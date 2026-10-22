"""The one operating release a server composes, shared by the API and the worker (#58 R58-RESEARCH-MOUNT-L2).

`main.create_app` (when no runtime is passed) and `investigation_jobs.main` both call `server_research_runtime`, so both
processes hold the same immutable runtime with the same release SHA-256; the existing admission check then refuses a
job whose frozen SHA-256 differs before any effect.

A release is composed only from a code-owned ACTUAL definition in `RELEASE_DEFINITIONS` whose exact SHA-256 is in
`operating_release.APPROVED_RELEASES`. Exactly one such release is registered (the MOE history plus Nansen
`actual-moe-history-nansen-20261022/1`), so the default server composes that one release: no release is read from a
setting, environment value, file or request, and composition reads no credential and opens no socket. Removing the
definition makes the default compose nothing again. See
`docs/qualification/research-provider-composition/MOE_HISTORY_ACTUAL_RELEASE.md`.

The history part binds the completed recorder run `moe-wmon-fwd20m-actual-20261022m` through anchor A: the exact
handoff and provenance texts and their hashes. Admission revalidates that graph before any credential read.

Credentials come from the process environment: unless a caller injects its own source, an approved release is composed
with the accepted `EnvironmentCredentialSource`, which reads an allowed slot only when a job prepares it. A missing or
blank slot refuses there, before any provider attempt. See
`docs/qualification/research-provider-composition/CREDENTIAL_DELIVERY.md`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from edge_os_api.core.hosted_deployment import HostedDeploymentRefused, check_hosted_deployment
from edge_os_api.core.research import operating_release
from edge_os_api.core.research.environment_credentials import EnvironmentCredentialSource
from edge_os_api.core.research.operating_release import (
    BINDING_FACT,
    HistoryRelease,
    NansenRelease,
    OperatingRelease,
    ReleaseRefused,
    release_sha256,
)
from edge_os_api.core.research.released_source_runtime import (
    CredentialSource,
    NansenHttpFactory,
    ReleasedSourceRuntime,
    open_released_runtime,
)
from edge_os_api.research_history.http_clients import StdlibHttpTransport

WMON = "0x3bd359c1119da7da1d913d1c4d2b7c461115433a"
MOE = "0xd8e004acba279417c04c0633cb5a21ceca207777"
MOE_POOL = "0x97199b34564911936bc850ac45ede785892b5aad"

# Anchor A: the exact artifacts of the completed run, kept in place. Its bytes enter the release SHA-256, so a
# changed run file, hash or window refuses at admission. The recorder produced it; this module only embeds it.
_MOE_HANDOFF_JSON = r'''{"accounting":{"admitted":{"hypersync":5,"quicknode":17},"ceilings":{"hypersync":9,"quicknode":17},"reply_bytes":589008,"resolved":22,"unknown_liability":0},"attempt_id":"moe-wmon-fwd20m-actual-20261022m","boundaries":{"B_ANCHOR":115553635,"B_END":115558005,"B_POST":115558006,"B_PRE":115554031,"B_START":115554032},"buckets":[{"end_utc":"2026-10-22T07:40:00Z","index":0,"payload_sha256":"1059afb58d3d2063e8eaa8abf7b7886091002262368b567a63914c22dc6bd347","reason":null,"received_at_utc":"2026-10-22T07:40:36Z","received_at_utc_us":1792654835730744,"record_count":4,"reply_body_sha256":"7c20b75a6e0cf131c8c29e5995dd4887fe78cea05e3fa64429a636f51d29b034","reply_id":"09-P3-hypersync","start_utc":"2026-10-22T07:35:00Z","status":"DELIVERED"},{"end_utc":"2026-10-22T07:45:00Z","index":1,"payload_sha256":"8151ff61871a4d0b74758d5a5904ee6fda63cde44a792748ea794213adf24d42","reason":null,"received_at_utc":"2026-10-22T07:45:33Z","received_at_utc_us":1792655132158329,"record_count":2,"reply_body_sha256":"2d141925eec8479ef24b43bffe7f7f4ea9d925f4b90b826e08de26fd05920a33","reply_id":"10-P3-hypersync","start_utc":"2026-10-22T07:40:00Z","status":"DELIVERED"},{"end_utc":"2026-10-22T07:50:00Z","index":2,"payload_sha256":"8206a26635cbb6a29320831a4955c224ddbf10796f5023e18ffa009446d52b72","reason":null,"received_at_utc":"2026-10-22T07:50:35Z","received_at_utc_us":1792655434764005,"record_count":4,"reply_body_sha256":"43188b5ba2f9fbe231fa95d1e0178a8e844b59126f5814b392af6358fb9f3b3a","reply_id":"11-P3-hypersync","start_utc":"2026-10-22T07:45:00Z","status":"DELIVERED"},{"end_utc":"2026-10-22T07:55:00Z","index":3,"payload_sha256":"31dda7169cbeaf0b82d5eecb8eb880ad0ab12447c70650de104f1102721e9210","reason":null,"received_at_utc":"2026-10-22T07:55:33Z","received_at_utc_us":1792655732532056,"record_count":4,"reply_body_sha256":"859281e5f148794324c8bb720f5fd8a059569bc99baab1ceff0fde637ecfb335","reply_id":"12-P3-hypersync","start_utc":"2026-10-22T07:50:00Z","status":"DELIVERED"}],"calls":[{"body_bytes":40,"body_sha256":"f2c8cfffaa48ef7411ca193dc71aba6aa88743516c723630eb7e5b6b2dc5b8ca","call_id":"01-P1-quicknode","outcome":"REPLY_RECEIVED","phase":"P1","provider":"quicknode","request_bytes":59,"request_sha256":"09fabe0af56b7726f1666ddd147482df4d951f86f66124b936716c53ab0e8471","slot":"chain_id","status":200},{"body_bytes":13298,"body_sha256":"995142ef8c4c8484717c0b774150a242f9fabe0e9056c4281bb3af2af9927b86","call_id":"02-P1-quicknode","outcome":"REPLY_RECEIVED","phase":"P1","provider":"quicknode","request_bytes":141,"request_sha256":"60a6ff2c082ae5a8a4e537026d88b997976c6e91b625d3270926efe4008335ac","slot":"creation_receipt","status":200},{"body_bytes":913,"body_sha256":"8db5b773029386af6445d66681e0a7ceb4a13fadb1d06974b489fffa2972b9ab","call_id":"03-P1-hypersync","outcome":"REPLY_RECEIVED","phase":"P1","provider":"hypersync","request_bytes":393,"request_sha256":"97354e5226bf67a2fde378a4fc8e9b752c069379d92ad2eb27e88fafec9215e1","slot":"creation_log","status":200},{"body_bytes":102,"body_sha256":"53dc9de6a2274f7fd9c75d2230cec9f36b54ca1ea150dc70460fbb39a844ba6c","call_id":"04-P1-quicknode","outcome":"REPLY_RECEIVED","phase":"P1","provider":"quicknode","request_bytes":136,"request_sha256":"2aa4900658dc2b27c00554e39bfd7481a043e98a4ed292d6fae988f88b630621","slot":"factory","status":200},{"body_bytes":128,"body_sha256":"c7a325ea90c96c23cf5cc70c8a0b1333379d27b065e7864384d9bbec3f50dc7d","call_id":"05-P1-quicknode","outcome":"REPLY_RECEIVED","phase":"P1","provider":"quicknode","request_bytes":112,"request_sha256":"5a1400e5a5ce048205cde4843dfabbd65f980993bd4fcd9df0ea9c0b7aa44907","slot":"code_pool","status":200},{"body_bytes":6536,"body_sha256":"e730f7885b17d84c3ada4d000749e382738e2a7491877907953db27f153fea04","call_id":"06-P1-quicknode","outcome":"REPLY_RECEIVED","phase":"P1","provider":"quicknode","request_bytes":112,"request_sha256":"bf71d7b5bc9dc6e52ca99a1ff996442a34dceb9acc0ad1117e03f9abf00cf113","slot":"code_token0","status":200},{"body_bytes":128,"body_sha256":"00e92f0b2ec1d4313dcbfed3c4b2a819808a65207786f863a89a6598e3c10221","call_id":"07-P1-quicknode","outcome":"REPLY_RECEIVED","phase":"P1","provider":"quicknode","request_bytes":112,"request_sha256":"8815903d916fad99d6b014d3c71366e60b801390e08e58850bd6d3e0c77cca83","slot":"code_token1","status":200},{"body_bytes":3262,"body_sha256":"69ecbef9829e4419b8f421a9eae79c4cef24ad8cc5ff35939f5b2920fa1f3dfa","call_id":"08-P2-quicknode","outcome":"REPLY_RECEIVED","phase":"P2","provider":"quicknode","request_bytes":82,"request_sha256":"38a161f3376c012276c3d6c9666dcbd4addcc3e56076a48d5d04e13fe2cd2b7d","slot":"anchor","status":200},{"body_bytes":185395,"body_sha256":"7c20b75a6e0cf131c8c29e5995dd4887fe78cea05e3fa64429a636f51d29b034","call_id":"09-P3-hypersync","outcome":"REPLY_RECEIVED","phase":"P3","provider":"hypersync","request_bytes":431,"request_sha256":"413fd0ed3f94bb41108e47c5e6f1280526015cbf0576c066417e55490f1778a5","slot":"bucket0_first","status":200},{"body_bytes":125015,"body_sha256":"2d141925eec8479ef24b43bffe7f7f4ea9d925f4b90b826e08de26fd05920a33","call_id":"10-P3-hypersync","outcome":"REPLY_RECEIVED","phase":"P3","provider":"hypersync","request_bytes":431,"request_sha256":"bea1c865e43dc3811dc8e193fcd2c7f93b9eb424bb9cc34bec4a25d683b81215","slot":"bucket1_first","status":200},{"body_bytes":123252,"body_sha256":"43188b5ba2f9fbe231fa95d1e0178a8e844b59126f5814b392af6358fb9f3b3a","call_id":"11-P3-hypersync","outcome":"REPLY_RECEIVED","phase":"P3","provider":"hypersync","request_bytes":431,"request_sha256":"7d5fb4337b8c9b3fc8f74560f85cdf4b2d6a4ea726ef8dbcedbe4364170dc0e0","slot":"bucket2_first","status":200},{"body_bytes":124151,"body_sha256":"859281e5f148794324c8bb720f5fd8a059569bc99baab1ceff0fde637ecfb335","call_id":"12-P3-hypersync","outcome":"REPLY_RECEIVED","phase":"P3","provider":"hypersync","request_bytes":431,"request_sha256":"d5a24ef4b42a5e38f17ab2cb657ed7057bcd0ad603d8a9183aecfa37dbe6fba5","slot":"bucket3_first","status":200},{"body_bytes":102,"body_sha256":"2f589b5f67d86de58d263e041a3360658e08b27fb6f5101af14b463e2488074a","call_id":"13-P4-quicknode","outcome":"REPLY_RECEIVED","phase":"P4","provider":"quicknode","request_bytes":139,"request_sha256":"5f1d55ce49f0afa8bb0efe1206c965848a80ed031e612740456dcbaa8da99f18","slot":"decimals_window_start_token1","status":200},{"body_bytes":102,"body_sha256":"2f589b5f67d86de58d263e041a3360658e08b27fb6f5101af14b463e2488074a","call_id":"14-P4-quicknode","outcome":"REPLY_RECEIVED","phase":"P4","provider":"quicknode","request_bytes":139,"request_sha256":"c08fbd0ba45e20668cd35a7830818382509b303b600be65516f599d65db12543","slot":"decimals_window_start_token0","status":200},{"body_bytes":102,"body_sha256":"e91dcfb3f1c840460ef48518d7ab7018fde6f3253b9fba0b033314e87890e4ad","call_id":"15-P4-quicknode","outcome":"REPLY_RECEIVED","phase":"P4","provider":"quicknode","request_bytes":139,"request_sha256":"4c7cf1a104e7dc0c3cdc66f030dcb724dda3625bd27057fed52f4da3346633d0","slot":"pool_token0","status":200},{"body_bytes":102,"body_sha256":"441b54a7452076de2469d685a07c5e79cd743288b5ed84c43a44f9a9d6d758aa","call_id":"16-P4-quicknode","outcome":"REPLY_RECEIVED","phase":"P4","provider":"quicknode","request_bytes":139,"request_sha256":"c22ea595a33ee37a27354076365327c18d2b2bcdac2628a3e97eac18693b3479","slot":"pool_token1","status":200},{"body_bytes":3193,"body_sha256":"679c838e8d7fa6632f193b790e5e821babf73c7859d65bd11d49c03d9d715259","call_id":"17-P5-quicknode","outcome":"REPLY_RECEIVED","phase":"P5","provider":"quicknode","request_bytes":85,"request_sha256":"b63919588b72d5384128905d70e0e05e5d51e2e68fea9b418a226849942af812","slot":"finalized","status":200},{"body_bytes":2779,"body_sha256":"4522d9db6e90a13b3f26cdc3f2f75e753ca8d7a9d791dfc990ec1f13f764325e","call_id":"18-P5-quicknode","outcome":"REPLY_RECEIVED","phase":"P5","provider":"quicknode","request_bytes":82,"request_sha256":"38a161f3376c012276c3d6c9666dcbd4addcc3e56076a48d5d04e13fe2cd2b7d","slot":"latest","status":200},{"body_bytes":102,"body_sha256":"2f589b5f67d86de58d263e041a3360658e08b27fb6f5101af14b463e2488074a","call_id":"19-P5-quicknode","outcome":"REPLY_RECEIVED","phase":"P5","provider":"quicknode","request_bytes":139,"request_sha256":"ef71244a8959df7f083bc350954abf5c89143dc6197cbb2589a04830dcec80e2","slot":"decimals_window_end_token1","status":200},{"body_bytes":102,"body_sha256":"2f589b5f67d86de58d263e041a3360658e08b27fb6f5101af14b463e2488074a","call_id":"20-P5-quicknode","outcome":"REPLY_RECEIVED","phase":"P5","provider":"quicknode","request_bytes":139,"request_sha256":"8865da988d8d2d815a9eef5d1829fda123aa16917513036ad2eb30b2bba25efc","slot":"decimals_window_end_token0","status":200},{"body_bytes":102,"body_sha256":"2f589b5f67d86de58d263e041a3360658e08b27fb6f5101af14b463e2488074a","call_id":"21-P5-quicknode","outcome":"REPLY_RECEIVED","phase":"P5","provider":"quicknode","request_bytes":136,"request_sha256":"b0d4ce3bfa2345a6a1110ac11f1bb36d91b02a4fc1f694648389f7787462a210","slot":"decimals_current_token1","status":200},{"body_bytes":102,"body_sha256":"2f589b5f67d86de58d263e041a3360658e08b27fb6f5101af14b463e2488074a","call_id":"22-P5-quicknode","outcome":"REPLY_RECEIVED","phase":"P5","provider":"quicknode","request_bytes":136,"request_sha256":"43917973cc45c4bc2c3e63c74fa04fe9df91ee9d703181fc11bcc1b55643f559","slot":"decimals_current_token0","status":200}],"canonicalization_version":"edge-os.forward-history-payload/1","chain_cursor":115558108,"claim_limit":"Construction and delivery evidence only; not authentication, rights or qualification.","clock":{"trusted":true},"decoder":"retained-v2-pair-created/1","delivery_records":{"2026-10-22T07:35:00Z":"2026-10-22T07:40:36Z","2026-10-22T07:40:00Z":"2026-10-22T07:45:33Z","2026-10-22T07:45:00Z":"2026-10-22T07:50:35Z","2026-10-22T07:50:00Z":"2026-10-22T07:55:33Z"},"evidence_class":"ACTUAL","evidence_notice":"Owned transport construction only; not provider authentication or rights.","facts":{"archive_height":115558107,"archive_height_declarable":true,"bytecode":{"pool":{"bytes":45,"sha256":"aae0c2751bc188e73da0773ae6f6b951aadb7dde6ccb0c0b22595a7f1541644d"},"token0":{"bytes":3249,"sha256":"1ba3ee06b3e4cd7beea3f1899cac23edb47876c45fceb320245d092ed2bfd187"},"token1":{"bytes":45,"sha256":"8822cfaa4ac24a2dee787fb37537ece3b6b4dfb178f859f00d97fa92376111a8"}},"creation_block_timestamp":1790221984,"decimals":{"current":{"token0":18,"token1":18},"window_end":{"token0":18,"token1":18},"window_start":{"token0":18,"token1":18}},"fee_transfer_semantics":"EXTERNAL_EVIDENCE_REQUIRED","finality_at_collection":"OBSERVED_FINAL","finalized":{"number":115558422,"observed_utc_us":1792655826519737,"timestamp":1792655825},"latest":{"number":115558428,"observed_utc_us":1792655827528409,"timestamp":1792655827},"pair_count":2854,"pool_tokens_at_start":{"token0":"READ","token1":"READ"}},"headers":[{"hash":"0xdb1cf9242323528cff973de11f111f4accaf6c05eece45522ac5efeadc044439","number":115553635,"timestamp":1792654380},{"hash":"0x88245a28adc0e108f1a312967404d774d6d5e444d961aa089a73bd20fe10184c","number":115554031,"timestamp":1792654499},{"hash":"0xbf0de2e95a3a58aad516f060d08aca5fcbd41b8a2decf46912e90658024dcb67","number":115554032,"timestamp":1792654500},{"hash":"0x8033858deae9ae544e8ea2ea15733e848c46cae227bbd5c7ef6a88a17079f8e9","number":115554044,"timestamp":1792654503},{"hash":"0x5332f436ab44403531222cae32cfe0814e82c88011e2b13b1ab0ce4c55aa9075","number":115554593,"timestamp":1792654669},{"hash":"0x0511715a9fb1ed709011407b3a985568895afc6bc5cb8a796b6163615799f6b3","number":115555241,"timestamp":1792654865},{"hash":"0x0afce34508d4d363759237af1f39edf75b568a0c26030c2c1b39cf522e7a41f2","number":115556019,"timestamp":1792655100},{"hash":"0x6f98a13404c5af9ee495313c9e76b60640521df823470d6c2a05ddc94a7284d0","number":115556023,"timestamp":1792655101},{"hash":"0x7d29918d3e4d4f9a7530eade0064644a234c420e14f1a9d1bfffa51c029d5751","number":115556504,"timestamp":1792655246},{"hash":"0x89b4e87cf336e8157979e337dfce7059e6f1dfece4f39d3dbaa78d507c307e6c","number":115556508,"timestamp":1792655247},{"hash":"0x1254f464edb8443e46853c0a8e67251efe860cbfb46f9197a3a6b191ba7a4b19","number":115557145,"timestamp":1792655440},{"hash":"0xb76d58d26744e1742eca5ca1960cf38b6874eb6911a38c66f69d53d0812366af","number":115557146,"timestamp":1792655440},{"hash":"0xdf0a999cc6017aa73125fadcae2a8151a1eed19a549677b94a04912705677bac","number":115557663,"timestamp":1792655596},{"hash":"0xeed073709c819dc9080c90d50281b85921f29c6d4ee36b199435f82dc2a76545","number":115557664,"timestamp":1792655596},{"hash":"0x18e93fd46f34254eb56f61b1c5ae19ce8f3e75e53b4859c83dc987f3eff078bf","number":115558005,"timestamp":1792655699},{"hash":"0xf4eda7ae2179e423fe5a51e36742bd392566cef4e9c8ace6e67478ac62e9d635","number":115558006,"timestamp":1792655700}],"input_schema":"edge-os.forward-history-input/1","input_sha256":"8566721a0e9988cd36a5ca4a396070fabfc9be8c3b611046cd98ea1c88773db8","market":{"base":"0xd8e004acba279417c04c0633cb5a21ceca207777","pool":"0x97199b34564911936bc850ac45ede785892b5aad","quote":"0x3bd359c1119da7da1d913d1c4d2b7c461115433a","token0":"0x3bd359c1119da7da1d913d1c4d2b7c461115433a","token1":"0xd8e004acba279417c04c0633cb5a21ceca207777"},"network":{"chain_id":143},"p3_replies":[{"archive_height":115555126,"call_id":"09-P3-hypersync","from_block":115553635,"log_count":4,"next_block":115555127,"received_utc_us":1792654835730744},{"archive_height":115556123,"call_id":"10-P3-hypersync","from_block":115555127,"log_count":4,"next_block":115556124,"received_utc_us":1792655132158329},{"archive_height":115557117,"call_id":"11-P3-hypersync","from_block":115556124,"log_count":2,"next_block":115557118,"received_utc_us":1792655434764005},{"archive_height":115558107,"call_id":"12-P3-hypersync","from_block":115557118,"log_count":4,"next_block":115558108,"received_utc_us":1792655732532056}],"phases":{"P1":{"outcome":"COMPLETED"},"P2":{"hash":"0xdb1cf9242323528cff973de11f111f4accaf6c05eece45522ac5efeadc044439","number":115553635,"observed_utc_us":1792654380525646,"outcome":"COMPLETED","timestamp":1792654380},"P3":{"outcome":"COMPLETED","reads":[{"bucket":0,"outcome":"COVERED","read":"first"},{"bucket":1,"outcome":"COVERED","read":"first"},{"bucket":2,"outcome":"COVERED","read":"first"},{"bucket":3,"outcome":"COVERED","read":"first"}]},"P4":{"outcome":"COMPLETED"},"P5":{"outcome":"COMPLETED"}},"predecessor_sha256":"c4fc01c4d498742cd9a904606135fdb2b27fea448bb254462a79a9f67824312f","query":{"address":"0x97199b34564911936bc850ac45ede785892b5aad","field_selection":{"block":["number","timestamp","hash"],"log":["address","topic0","topic1","topic2","topic3","data","block_number","block_hash","transaction_hash","transaction_index","log_index","removed"]},"include_all_blocks":true,"max_num_blocks":10000,"topic0":"0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"},"recorder_code_sha256":"e02f3cac6a4500c3c9359544cb064e86671cc16074428b2a5863e51089f77395","release_frozen":false,"requested_evidence_class":"ACTUAL","scan":{"from_block":115554031,"to_block_exclusive":115558007},"scan_log_count":14,"schema_version":"edge-os.forward-history-handoff/2","source_id":"actual-moe-wmon-fwd20m/1","status":"COMPLETED","stop_reason":null,"transport":{"construction":"OWNED_STDLIB","implementation":"edge_os_api.research_history.http_clients.http_transport.StdlibHttpTransport","implementation_sha256":"89aa0a18442fb1a28a51d31a9a06da2da9fee4f3e2731239e34a00d44c725f0d"},"weaker_evidence":[],"window":{"bucket_seconds":300,"end_utc":"2026-10-22T07:55:00Z","start_utc":"2026-10-22T07:35:00Z"}}'''
_MOE_PROVENANCE_JSON = r'''{"attempt_id":"moe-wmon-fwd20m-actual-20261022m","handoff_sha256":"da8b5bf992471dd5fafd832a8d8473524af72cb3a3013a201d5ea3045390ebee","receipts_json":"{\"attempt_id\":\"moe-wmon-fwd20m-actual-20261022m\",\"evidence_class\":\"ACTUAL\",\"handoff_sha256\":\"da8b5bf992471dd5fafd832a8d8473524af72cb3a3013a201d5ea3045390ebee\",\"receipts\":[{\"body_bytes\":40,\"body_sha256\":\"f2c8cfffaa48ef7411ca193dc71aba6aa88743516c723630eb7e5b6b2dc5b8ca\",\"call_id\":\"01-P1-quicknode\",\"elapsed_us\":1634446,\"outcome\":\"REPLY_RECEIVED\",\"received_at_utc_us\":1792653608123165,\"request_sha256\":\"09fabe0af56b7726f1666ddd147482df4d951f86f66124b936716c53ab0e8471\",\"status\":200,\"transport_binding_sha256\":\"92bc0ecd135473d35cc21ef313655174d2efc215d391794c5c72b72ee8436c31\"},{\"body_bytes\":13298,\"body_sha256\":\"995142ef8c4c8484717c0b774150a242f9fabe0e9056c4281bb3af2af9927b86\",\"call_id\":\"02-P1-quicknode\",\"elapsed_us\":1011305,\"outcome\":\"REPLY_RECEIVED\",\"received_at_utc_us\":1792653609136865,\"request_sha256\":\"60a6ff2c082ae5a8a4e537026d88b997976c6e91b625d3270926efe4008335ac\",\"status\":200,\"transport_binding_sha256\":\"92bc0ecd135473d35cc21ef313655174d2efc215d391794c5c72b72ee8436c31\"},{\"body_bytes\":913,\"body_sha256\":\"8db5b773029386af6445d66681e0a7ceb4a13fadb1d06974b489fffa2972b9ab\",\"call_id\":\"03-P1-hypersync\",\"elapsed_us\":1603840,\"outcome\":\"REPLY_RECEIVED\",\"received_at_utc_us\":1792653610742025,\"request_sha256\":\"97354e5226bf67a2fde378a4fc8e9b752c069379d92ad2eb27e88fafec9215e1\",\"status\":200,\"transport_binding_sha256\":\"92bc0ecd135473d35cc21ef313655174d2efc215d391794c5c72b72ee8436c31\"},{\"body_bytes\":102,\"body_sha256\":\"53dc9de6a2274f7fd9c75d2230cec9f36b54ca1ea150dc70460fbb39a844ba6c\",\"call_id\":\"04-P1-quicknode\",\"elapsed_us\":1312562,\"outcome\":\"REPLY_RECEIVED\",\"received_at_utc_us\":1792653612061450,\"request_sha256\":\"2aa4900658dc2b27c00554e39bfd7481a043e98a4ed292d6fae988f88b630621\",\"status\":200,\"transport_binding_sha256\":\"92bc0ecd135473d35cc21ef313655174d2efc215d391794c5c72b72ee8436c31\"},{\"body_bytes\":128,\"body_sha256\":\"c7a325ea90c96c23cf5cc70c8a0b1333379d27b065e7864384d9bbec3f50dc7d\",\"call_id\":\"05-P1-quicknode\",\"elapsed_us\":470454,\"outcome\":\"REPLY_RECEIVED\",\"received_at_utc_us\":1792653612534170,\"request_sha256\":\"5a1400e5a5ce048205cde4843dfabbd65f980993bd4fcd9df0ea9c0b7aa44907\",\"status\":200,\"transport_binding_sha256\":\"92bc0ecd135473d35cc21ef313655174d2efc215d391794c5c72b72ee8436c31\"},{\"body_bytes\":6536,\"body_sha256\":\"e730f7885b17d84c3ada4d000749e382738e2a7491877907953db27f153fea04\",\"call_id\":\"06-P1-quicknode\",\"elapsed_us\":1494618,\"outcome\":\"REPLY_RECEIVED\",\"received_at_utc_us\":1792653614566825,\"request_sha256\":\"bf71d7b5bc9dc6e52ca99a1ff996442a34dceb9acc0ad1117e03f9abf00cf113\",\"status\":200,\"transport_binding_sha256\":\"92bc0ecd135473d35cc21ef313655174d2efc215d391794c5c72b72ee8436c31\"},{\"body_bytes\":128,\"body_sha256\":\"00e92f0b2ec1d4313dcbfed3c4b2a819808a65207786f863a89a6598e3c10221\",\"call_id\":\"07-P1-quicknode\",\"elapsed_us\":462765,\"outcome\":\"REPLY_RECEIVED\",\"received_at_utc_us\":1792653615034629,\"request_sha256\":\"8815903d916fad99d6b014d3c71366e60b801390e08e58850bd6d3e0c77cca83\",\"status\":200,\"transport_binding_sha256\":\"92bc0ecd135473d35cc21ef313655174d2efc215d391794c5c72b72ee8436c31\"},{\"body_bytes\":3262,\"body_sha256\":\"69ecbef9829e4419b8f421a9eae79c4cef24ad8cc5ff35939f5b2920fa1f3dfa\",\"call_id\":\"08-P2-quicknode\",\"elapsed_us\":508577,\"outcome\":\"REPLY_RECEIVED\",\"received_at_utc_us\":1792654380525646,\"request_sha256\":\"38a161f3376c012276c3d6c9666dcbd4addcc3e56076a48d5d04e13fe2cd2b7d\",\"status\":200,\"transport_binding_sha256\":\"92bc0ecd135473d35cc21ef313655174d2efc215d391794c5c72b72ee8436c31\"},{\"body_bytes\":185395,\"body_sha256\":\"7c20b75a6e0cf131c8c29e5995dd4887fe78cea05e3fa64429a636f51d29b034\",\"call_id\":\"09-P3-hypersync\",\"elapsed_us\":5704016,\"outcome\":\"REPLY_RECEIVED\",\"received_at_utc_us\":1792654835730744,\"request_sha256\":\"413fd0ed3f94bb41108e47c5e6f1280526015cbf0576c066417e55490f1778a5\",\"status\":200,\"transport_binding_sha256\":\"92bc0ecd135473d35cc21ef313655174d2efc215d391794c5c72b72ee8436c31\"},{\"body_bytes\":125015,\"body_sha256\":\"2d141925eec8479ef24b43bffe7f7f4ea9d925f4b90b826e08de26fd05920a33\",\"call_id\":\"10-P3-hypersync\",\"elapsed_us\":2140829,\"outcome\":\"REPLY_RECEIVED\",\"received_at_utc_us\":1792655132158329,\"request_sha256\":\"bea1c865e43dc3811dc8e193fcd2c7f93b9eb424bb9cc34bec4a25d683b81215\",\"status\":200,\"transport_binding_sha256\":\"92bc0ecd135473d35cc21ef313655174d2efc215d391794c5c72b72ee8436c31\"},{\"body_bytes\":123252,\"body_sha256\":\"43188b5ba2f9fbe231fa95d1e0178a8e844b59126f5814b392af6358fb9f3b3a\",\"call_id\":\"11-P3-hypersync\",\"elapsed_us\":4726167,\"outcome\":\"REPLY_RECEIVED\",\"received_at_utc_us\":1792655434764005,\"request_sha256\":\"7d5fb4337b8c9b3fc8f74560f85cdf4b2d6a4ea726ef8dbcedbe4364170dc0e0\",\"status\":200,\"transport_binding_sha256\":\"92bc0ecd135473d35cc21ef313655174d2efc215d391794c5c72b72ee8436c31\"},{\"body_bytes\":124151,\"body_sha256\":\"859281e5f148794324c8bb720f5fd8a059569bc99baab1ceff0fde637ecfb335\",\"call_id\":\"12-P3-hypersync\",\"elapsed_us\":2501234,\"outcome\":\"REPLY_RECEIVED\",\"received_at_utc_us\":1792655732532056,\"request_sha256\":\"d5a24ef4b42a5e38f17ab2cb657ed7057bcd0ad603d8a9183aecfa37dbe6fba5\",\"status\":200,\"transport_binding_sha256\":\"92bc0ecd135473d35cc21ef313655174d2efc215d391794c5c72b72ee8436c31\"},{\"body_bytes\":102,\"body_sha256\":\"2f589b5f67d86de58d263e041a3360658e08b27fb6f5101af14b463e2488074a\",\"call_id\":\"13-P4-quicknode\",\"elapsed_us\":1508870,\"outcome\":\"REPLY_RECEIVED\",\"received_at_utc_us\":1792655822566989,\"request_sha256\":\"5f1d55ce49f0afa8bb0efe1206c965848a80ed031e612740456dcbaa8da99f18\",\"status\":200,\"transport_binding_sha256\":\"92bc0ecd135473d35cc21ef313655174d2efc215d391794c5c72b72ee8436c31\"},{\"body_bytes\":102,\"body_sha256\":\"2f589b5f67d86de58d263e041a3360658e08b27fb6f5101af14b463e2488074a\",\"call_id\":\"14-P4-quicknode\",\"elapsed_us\":464450,\"outcome\":\"REPLY_RECEIVED\",\"received_at_utc_us\":1792655823045758,\"request_sha256\":\"c08fbd0ba45e20668cd35a7830818382509b303b600be65516f599d65db12543\",\"status\":200,\"transport_binding_sha256\":\"92bc0ecd135473d35cc21ef313655174d2efc215d391794c5c72b72ee8436c31\"},{\"body_bytes\":102,\"body_sha256\":\"e91dcfb3f1c840460ef48518d7ab7018fde6f3253b9fba0b033314e87890e4ad\",\"call_id\":\"15-P4-quicknode\",\"elapsed_us\":1463881,\"outcome\":\"REPLY_RECEIVED\",\"received_at_utc_us\":1792655825045751,\"request_sha256\":\"4c7cf1a104e7dc0c3cdc66f030dcb724dda3625bd27057fed52f4da3346633d0\",\"status\":200,\"transport_binding_sha256\":\"92bc0ecd135473d35cc21ef313655174d2efc215d391794c5c72b72ee8436c31\"},{\"body_bytes\":102,\"body_sha256\":\"441b54a7452076de2469d685a07c5e79cd743288b5ed84c43a44f9a9d6d758aa\",\"call_id\":\"16-P4-quicknode\",\"elapsed_us\":468657,\"outcome\":\"REPLY_RECEIVED\",\"received_at_utc_us\":1792655825518098,\"request_sha256\":\"c22ea595a33ee37a27354076365327c18d2b2bcdac2628a3e97eac18693b3479\",\"status\":200,\"transport_binding_sha256\":\"92bc0ecd135473d35cc21ef313655174d2efc215d391794c5c72b72ee8436c31\"},{\"body_bytes\":3193,\"body_sha256\":\"679c838e8d7fa6632f193b790e5e821babf73c7859d65bd11d49c03d9d715259\",\"call_id\":\"17-P5-quicknode\",\"elapsed_us\":466071,\"outcome\":\"REPLY_RECEIVED\",\"received_at_utc_us\":1792655826519737,\"request_sha256\":\"b63919588b72d5384128905d70e0e05e5d51e2e68fea9b418a226849942af812\",\"status\":200,\"transport_binding_sha256\":\"92bc0ecd135473d35cc21ef313655174d2efc215d391794c5c72b72ee8436c31\"},{\"body_bytes\":2779,\"body_sha256\":\"4522d9db6e90a13b3f26cdc3f2f75e753ca8d7a9d791dfc990ec1f13f764325e\",\"call_id\":\"18-P5-quicknode\",\"elapsed_us\":465148,\"outcome\":\"REPLY_RECEIVED\",\"received_at_utc_us\":1792655827528409,\"request_sha256\":\"38a161f3376c012276c3d6c9666dcbd4addcc3e56076a48d5d04e13fe2cd2b7d\",\"status\":200,\"transport_binding_sha256\":\"92bc0ecd135473d35cc21ef313655174d2efc215d391794c5c72b72ee8436c31\"},{\"body_bytes\":102,\"body_sha256\":\"2f589b5f67d86de58d263e041a3360658e08b27fb6f5101af14b463e2488074a\",\"call_id\":\"19-P5-quicknode\",\"elapsed_us\":1326741,\"outcome\":\"REPLY_RECEIVED\",\"received_at_utc_us\":1792655829394051,\"request_sha256\":\"ef71244a8959df7f083bc350954abf5c89143dc6197cbb2589a04830dcec80e2\",\"status\":200,\"transport_binding_sha256\":\"92bc0ecd135473d35cc21ef313655174d2efc215d391794c5c72b72ee8436c31\"},{\"body_bytes\":102,\"body_sha256\":\"2f589b5f67d86de58d263e041a3360658e08b27fb6f5101af14b463e2488074a\",\"call_id\":\"20-P5-quicknode\",\"elapsed_us\":461038,\"outcome\":\"REPLY_RECEIVED\",\"received_at_utc_us\":1792655829857539,\"request_sha256\":\"8865da988d8d2d815a9eef5d1829fda123aa16917513036ad2eb30b2bba25efc\",\"status\":200,\"transport_binding_sha256\":\"92bc0ecd135473d35cc21ef313655174d2efc215d391794c5c72b72ee8436c31\"},{\"body_bytes\":102,\"body_sha256\":\"2f589b5f67d86de58d263e041a3360658e08b27fb6f5101af14b463e2488074a\",\"call_id\":\"21-P5-quicknode\",\"elapsed_us\":1501462,\"outcome\":\"REPLY_RECEIVED\",\"received_at_utc_us\":1792655831898687,\"request_sha256\":\"b0d4ce3bfa2345a6a1110ac11f1bb36d91b02a4fc1f694648389f7787462a210\",\"status\":200,\"transport_binding_sha256\":\"92bc0ecd135473d35cc21ef313655174d2efc215d391794c5c72b72ee8436c31\"},{\"body_bytes\":102,\"body_sha256\":\"2f589b5f67d86de58d263e041a3360658e08b27fb6f5101af14b463e2488074a\",\"call_id\":\"22-P5-quicknode\",\"elapsed_us\":460276,\"outcome\":\"REPLY_RECEIVED\",\"received_at_utc_us\":1792655832360571,\"request_sha256\":\"43917973cc45c4bc2c3e63c74fa04fe9df91ee9d703181fc11bcc1b55643f559\",\"status\":200,\"transport_binding_sha256\":\"92bc0ecd135473d35cc21ef313655174d2efc215d391794c5c72b72ee8436c31\"}],\"recorder_code_sha256\":\"e02f3cac6a4500c3c9359544cb064e86671cc16074428b2a5863e51089f77395\",\"schema_version\":\"edge-os.forward-history-transport-receipts/1\",\"transport\":{\"construction\":\"OWNED_STDLIB\",\"implementation\":\"edge_os_api.research_history.http_clients.http_transport.StdlibHttpTransport\",\"implementation_sha256\":\"89aa0a18442fb1a28a51d31a9a06da2da9fee4f3e2731239e34a00d44c725f0d\"}}","receipts_sha256":"f6ec0710d9dae26ad72ef3dca6f0f78062815a81c6eb96cda409881eea463332","recorder_code_sha256":"e02f3cac6a4500c3c9359544cb064e86671cc16074428b2a5863e51089f77395","schema_version":"edge-os.forward-history-provenance/1","transport":{"construction":"OWNED_STDLIB","implementation":"edge_os_api.research_history.http_clients.http_transport.StdlibHttpTransport","implementation_sha256":"89aa0a18442fb1a28a51d31a9a06da2da9fee4f3e2731239e34a00d44c725f0d"}}'''
_MOE_ANCHOR = {
    "schema_version": "edge-os.forward-history-binding/2",
    "handoff_json": _MOE_HANDOFF_JSON,
    "handoff_sha256": "da8b5bf992471dd5fafd832a8d8473524af72cb3a3013a201d5ea3045390ebee",
    "receipts_sha256": "f6ec0710d9dae26ad72ef3dca6f0f78062815a81c6eb96cda409881eea463332",
    "provenance_json": _MOE_PROVENANCE_JSON,
    "provenance_sha256": "fdea4dca865d2b6c1fa6599e818ea20758994d7686ddde0c845c98e3cf2ae5f2",
}

_MOE_PROFILE = {
    "schema_version": "p07.market_dataset_profile/1",
    "profile_id": "actual-moe-wmon-fwd20m-20261022m/1",
    "evidence_class": "REAL_SOURCE",
    "network": {"network": "MONAD", "chain_id": 143, "chain_id_source": "PROVIDER_READ"},
    "venue": {"underlying_venue": "uniswap-v2-compatible-monad-mainnet/1",
              "pool_family": "UNISWAP_V2_COMPATIBLE", "pool_address": MOE_POOL},
    "pool_tokens": [
        {"address": WMON, "symbol_label": "WMON", "kind": "ERC20", "decimals": 18, "role": "QUOTE"},
        {"address": MOE, "symbol_label": "MOE", "kind": "ERC20", "decimals": 18, "role": "BASE"},
    ],
    "orientation": "QUOTE_PER_BASE",
    "event": {"event_schema_version": "uniswap-v2-swap/1",
              "signature": "Swap(address,uint256,uint256,uint256,uint256,address)",
              "topic0": "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"},
    "conversion": {"amount_conversion_version": "v2-swap-quote-per-base-pool-gross/1",
                   "numeric": "decimal-50-half-even/1", "measurement": "POOL_GROSS"},
    "resolution": {"bucket_seconds": 300, "interval": "[start,end)"},
    "ordering": {"key": ["block_number", "transaction_index", "log_index"]},
    "source": {"history_provider": "ENVIO_HYPERSYNC", "corroboration_provider": "QUICKNODE_JSON_RPC",
               "data_route": "ENVIO_QUICKNODE_CORROBORATED"},
    "availability": {"model": "OBSERVED_DELIVERY", "basis_evidence": "SOURCE_DELIVERY_RECORD"},
    "finality": {"depth_blocks": 2, "basis": "DOCUMENTATION"},
    "execution_route": {"adapter": "KURU_FLOW_FIXED_INPUT", "identity": None, "identity_state": "UNKNOWN",
                        "qualification": "UNQUALIFIED"},
    "unmodeled_effects": ["TRANSFER_OR_REFLECTION", "WRAPPING", "ROUTING", "GAS", "PRICE_IMPACT", "CAPACITY"],
    "dataset": {
        "window": {"start_utc": "2026-10-22T07:35:00Z", "end_utc": "2026-10-22T07:55:00Z"},
        "collection": {"collected_at_utc": "2026-10-22T07:57:07Z", "collected_on_utc": None,
                       "archive_height": 115558107},
        "query": {"identity_sha256": None, "definition": None,
                  "from_block": 115554031, "to_block_exclusive": 115558007},
        "pages": [],
        "dataset_revision": {"basis": "NONE", "manifest_sha256": None, "page_count": 0, "row_count": None},
    },
}

# Facts the release declares. The anchored run supports each value; the recorder's delivery records let the saved
# buckets reproduce the anchored availability times. Token mechanics carries its observed-behavior basis by hash.
_MOE_PROVIDER_FACTS = {
    "collected_at_utc": "2026-10-22T07:57:07Z",
    "archive_height": 115558107,
    "chain_id_source": "PROVIDER_READ",
    "pool_tokens": "SINGLE_READ",
    "pool_venue": "SINGLE_SOURCE",
    "decimals": {"base": {"window_start": "READ", "window_end": "READ", "current": "READ"},
                 "quote": {"window_start": "READ", "window_end": "READ", "current": "READ"}},
    "fee_transfer_semantics": "QUALIFIED_BY_OBSERVATION",
    "token_mechanics": {"state": "QUALIFIED_BY_OBSERVATION", "basis": "OBSERVED_BEHAVIOR",
                        "window_seconds": 43200,
                        "evidence_sha256": "5ad3a7c3e11f48e6f32fe2ab9f1edf7bf968962e4854c98d16e70327cfc9e73b",
                        "source_proof": False},
    "corroboration": {},
    "finality_at_collection": "OBSERVED_FINAL",
    "delivery_records": {"2026-10-22T07:35:00Z": "2026-10-22T07:40:36Z",
                         "2026-10-22T07:40:00Z": "2026-10-22T07:45:33Z",
                         "2026-10-22T07:45:00Z": "2026-10-22T07:50:35Z",
                         "2026-10-22T07:50:00Z": "2026-10-22T07:55:33Z"},
    "feasibility_claim": {
        "schedule": {"anchor_utc": "2026-10-22T07:35:00Z", "period_seconds": 300, "feature_end_offset_seconds": 0},
        "horizon_seconds": 300, "reference_window_seconds": 300, "warmup_buckets": 0,
        "partitions": [{"name": "moe-window", "start_utc": "2026-10-22T07:35:00Z", "end_utc": "2026-10-22T07:55:00Z",
                        "required_triggered": 1, "required_control": 1}],
    },
    "factory": "0xa25b13127e63ddae6d0b35570ff3d39dbd621001",
    "topic0": "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822",
    "environments": {"quicknode_host": "virulent-necessary-patina.monad-mainnet.quiknode.pro",
                     "hypersync_endpoint": "https://monad.hypersync.xyz",
                     "source_lookup": "https://sourcify-api-monad.blockvision.org/",
                     "moe_source": "NOT_VERIFIED"},
}


def _moe_history() -> HistoryRelease:
    return HistoryRelease(
        source_id="actual-moe-wmon-fwd20m/1",
        title="MOE/WMON actual forward history (20 minutes, 2026-10-22)",
        envio_endpoint="https://monad.hypersync.xyz",
        envio_credential_slot="HYPERSYNC_API_KEY",
        quicknode_host="virulent-necessary-patina.monad-mainnet.quiknode.pro",
        quicknode_credential_slot="QUICKNODE_API_URL",
        profile=_MOE_PROFILE,
        scan={"from_block": 115554031, "to_block_exclusive": 115558007},
        corroboration_sample_size=8,
        provider_facts={BINDING_FACT: _MOE_ANCHOR, **_MOE_PROVIDER_FACTS},
        limits={"provider_requests": 13, "compute_seconds": 600, "max_pages": 4, "max_rows": 2000,
                "max_bytes": 4194304, "deadline_seconds": 600},
        client_bounds={"deadline_seconds": 120, "connect_timeout_seconds": 15,
                       "max_response_bytes": 2097152, "max_request_bytes": 65536, "max_blocks_per_page": 10000},
    )


def _moe_nansen() -> NansenRelease:
    return NansenRelease(
        endpoint="https://api.nansen.ai",
        credential_slot="NANSEN_API_KEY",
        token_address=MOE,
        token_symbol="MOE",
        window={"start_utc": "2026-10-21T07:55:00Z", "end_utc": "2026-10-22T07:55:00Z"},
        operations=("holders", "flows"),
        holder_query={"label_type": "all_holders", "aggregate_by_entity": False,
                      "order_field": "token_amount", "value_usd_min": None},
        flow_query={"label": "top_100_holders"},
        limits={"max_requests": 2, "max_pages": 1, "max_bytes": 2000000, "max_credits": "6", "per_page": 100},
        deadline_seconds=300,
        compute_seconds=300,
        client_bounds={"connect_timeout_seconds": 10, "max_request_bytes": 16384,
                       "max_response_bytes": 1000000},
    )


# Release id -> its ACTUAL definition. Exactly one approved actual release is registered below. Adding, changing or
# removing one is a reviewed code change together with its `APPROVED_RELEASES` entry.
RELEASE_DEFINITIONS: Mapping[str, OperatingRelease] = {
    "actual-moe-history-nansen-20261022/1": OperatingRelease(
        release_id="actual-moe-history-nansen-20261022/1",
        kind="ACTUAL",
        history=_moe_history(),
        nansen=_moe_nansen(),
    ),
}


def server_research_runtime(settings: Any, *,
                            credentials: CredentialSource | None = None) -> ReleasedSourceRuntime | None:
    """The server's composed release, or None. Reads no credential and opens no socket. Raises `ReleaseRefused`.

    `credentials` replaces the environment source; it is used as given, never with a fallback."""
    if any(key != release.release_id for key, release in RELEASE_DEFINITIONS.items()):
        raise ReleaseRefused("operating_release_invalid", "a release definition is filed under another id")
    approved = [release for release in RELEASE_DEFINITIONS.values() if release.kind == "ACTUAL"
                and operating_release.APPROVED_RELEASES.get(release.release_id) == release_sha256(release)]
    if not approved:
        return None
    if len(approved) > 1:
        raise ReleaseRefused("operating_release_invalid", "a server composes at most one approved release")
    release = approved[0]
    if settings.env == "production":
        # The API and the worker share this gate: no approved research release composes without a matching record.
        try:
            deployment = check_hosted_deployment(settings)
        except HostedDeploymentRefused as refused:
            raise ReleaseRefused(
                "hosted_deployment_refused",
                f"the approved research release needs an approved hosted deployment ({refused.code})") from None
        if deployment is None or not deployment.admits_research_release(release.release_id, release_sha256(release)):
            raise ReleaseRefused("hosted_deployment_not_matched",
                                 "no approved hosted deployment record names this exact research release")
    source = EnvironmentCredentialSource() if credentials is None else credentials
    return open_released_runtime(settings, release, credentials=source,
                                 http_transport=StdlibHttpTransport if release.history is not None else None,
                                 nansen_transport=NansenHttpFactory() if release.nansen is not None else None)
