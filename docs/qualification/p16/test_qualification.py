import tempfile
import unittest
from pathlib import Path

from qualification import Binding, Position, SetupManager, SetupLedger, FakePrivy


class P16QualificationTests(unittest.TestCase):
    def test_local_binding_rejects_changed_owner_agent_wallet_network_and_position(self) -> None:
        expected = Binding("owner-a", "agent-a", "wallet-a", 10143, "position-a")
        fields = {
            "owner_id": "owner-b",
            "agent_id": "agent-b",
            "wallet_id": "wallet-b",
            "network_id": 143,
            "position_id": "position-b",
        }
        for field, value in fields.items():
            with self.subTest(field=field):
                changed = expected.with_value(field, value)
                self.assertFalse(expected.matches(changed))

    def test_same_token_positions_keep_separate_agent_wallet_and_owner_bindings(self) -> None:
        first = Position(
            Binding("owner-a", "agent-a", "wallet-a", 10143, "position-a"),
            "monad-testnet:10143/asset:TEST",
            "500",
        )
        second = Position(
            Binding("owner-a", "agent-b", "wallet-b", 10143, "position-b"),
            "monad-testnet:10143/asset:TEST",
            "900",
        )
        third = Position(
            Binding("owner-b", "agent-c", "wallet-c", 10143, "position-c"),
            "monad-testnet:10143/asset:TEST",
            "700",
        )

        self.assertEqual({first.asset_id, second.asset_id, third.asset_id}, {first.asset_id})
        self.assertEqual(
            {first.binding.owner_id, second.binding.owner_id, third.binding.owner_id},
            {"owner-a", "owner-b"},
        )
        self.assertNotEqual(first.binding.position_id, second.binding.position_id)
        self.assertFalse(first.binding.matches(second.binding))
        self.assertFalse(first.binding.matches(third.binding))

    def test_lost_create_response_restarts_with_same_setup_and_idempotency_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "setup.json"
            ledger = SetupLedger(path)
            provider = FakePrivy()
            first = SetupManager(ledger, provider)

            state = first.create("setup-a", "owner-a", "agent-a", lose_response=True)
            self.assertEqual(state, "UNKNOWN")
            self.assertEqual(ledger.get("setup-a")["state"], "UNKNOWN")

            restarted = SetupManager(SetupLedger(path), provider)
            state = restarted.resume("setup-a")
            record = restarted.ledger.get("setup-a")

            self.assertEqual(state, "CONFIRMED")
            self.assertEqual(record["wallet_id"], "wallet-1")
            self.assertEqual(record["external_id"], "edgeos_setup-a")
            self.assertEqual(provider.create_count, 1)

    def test_cancel_before_send_does_not_create_a_wallet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = FakePrivy()
            manager = SetupManager(
                SetupLedger(Path(directory) / "setup.json"), provider
            )
            manager.prepare("setup-a", "owner-a", "agent-a")

            self.assertEqual(manager.cancel("setup-a"), "CANCELLED")
            self.assertEqual(manager.resume("setup-a"), "CANCELLED")
            self.assertEqual(provider.create_count, 0)

    def test_cancel_after_lost_response_keeps_setup_unknown_for_reconciliation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "setup.json"
            provider = FakePrivy()
            manager = SetupManager(SetupLedger(path), provider)
            self.assertEqual(
                manager.create("setup-a", "owner-a", "agent-a", lose_response=True),
                "UNKNOWN",
            )

            self.assertEqual(manager.cancel("setup-a"), "UNKNOWN")
            restarted = SetupManager(SetupLedger(path), provider)
            self.assertEqual(restarted.resume("setup-a"), "CONFIRMED")
            self.assertEqual(provider.create_count, 1)

    def test_crash_after_provider_acceptance_stays_unknown_and_recovers(self) -> None:
        class CrashAfterAcceptance(FakePrivy):
            def create_wallet(self, **kwargs):
                super().create_wallet(**kwargs)
                raise SystemExit("simulated process interruption")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "setup.json"
            provider = CrashAfterAcceptance()
            manager = SetupManager(SetupLedger(path), provider)
            prepared = manager.prepare("setup-a", "owner-a", "agent-a")
            setup_key = prepared["idempotency_key"]

            with self.assertRaises(SystemExit):
                manager.create("setup-a", "owner-a", "agent-a")

            restarted = SetupManager(SetupLedger(path), provider)
            record = restarted.ledger.get("setup-a")
            self.assertEqual(record["state"], "UNKNOWN")
            self.assertEqual(record["idempotency_key"], setup_key)
            self.assertEqual(restarted.cancel("setup-a"), "UNKNOWN")
            self.assertEqual(restarted.resume("setup-a"), "CONFIRMED")
            self.assertEqual(restarted.ledger.get("setup-a")["wallet_id"], "wallet-1")
            self.assertEqual(provider.create_count, 1)

    def test_malformed_create_responses_stay_unknown_and_reconcile(self) -> None:
        for malformed in ({}, {"wallet_id": ""}):
            with self.subTest(response=malformed):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "setup.json"
                    provider = FakePrivy()
                    create_wallet = provider.create_wallet

                    def create_then_return_malformed(**kwargs):
                        create_wallet(**kwargs)
                        return malformed

                    provider.create_wallet = create_then_return_malformed
                    manager = SetupManager(SetupLedger(path), provider)
                    prepared = manager.prepare("setup-a", "owner-a", "agent-a")
                    setup_key = prepared["idempotency_key"]

                    self.assertEqual(
                        manager.create("setup-a", "owner-a", "agent-a"),
                        "UNKNOWN",
                    )
                    self.assertEqual(manager.cancel("setup-a"), "UNKNOWN")

                    restarted = SetupManager(SetupLedger(path), provider)
                    self.assertEqual(restarted.resume("setup-a"), "CONFIRMED")
                    record = restarted.ledger.get("setup-a")
                    self.assertEqual(record["wallet_id"], "wallet-1")
                    self.assertEqual(record["idempotency_key"], setup_key)
                    self.assertEqual(provider.create_count, 1)

    def test_unknown_reconciles_after_idempotency_cache_is_gone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "setup.json"
            provider = FakePrivy()
            manager = SetupManager(SetupLedger(path), provider)
            self.assertEqual(
                manager.create("setup-a", "owner-a", "agent-a", lose_response=True),
                "UNKNOWN",
            )
            setup_key = manager.ledger.get("setup-a")["idempotency_key"]
            provider.idempotency.clear()

            restarted = SetupManager(SetupLedger(path), provider)
            self.assertEqual(restarted.resume("setup-a"), "CONFIRMED")
            self.assertEqual(restarted.ledger.get("setup-a")["wallet_id"], "wallet-1")
            self.assertEqual(restarted.ledger.get("setup-a")["idempotency_key"], setup_key)
            self.assertEqual(provider.create_count, 1)

    def test_unknown_does_not_retry_when_lookup_is_ambiguous_mismatched_or_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for outcome in ("ambiguous", "mismatched", "unavailable"):
                with self.subTest(outcome=outcome):
                    path = Path(directory) / f"{outcome}.json"
                    provider = FakePrivy()
                    manager = SetupManager(SetupLedger(path), provider)
                    self.assertEqual(
                        manager.create(
                            f"setup-{outcome}", "owner-a", "agent-a", lose_response=True
                        ),
                        "UNKNOWN",
                    )
                    record = manager.ledger.get(f"setup-{outcome}")
                    setup_key = record["idempotency_key"]
                    external_id = record["external_id"]

                    if outcome == "ambiguous":
                        provider.create_wallet(
                            idempotency_key="second-wallet",
                            request={
                                "owner_id": "owner-a",
                                "agent_id": "agent-a",
                                "chain_type": "ethereum",
                                "network_id": 10143,
                                "external_id": external_id,
                            },
                        )
                    elif outcome == "mismatched":
                        provider.wallets["wallet-1"]["owner_id"] = "owner-b"
                    else:
                        provider.lookup_unavailable = True

                    restarted = SetupManager(SetupLedger(path), provider)
                    self.assertEqual(
                        restarted.resume(f"setup-{outcome}"), "UNKNOWN"
                    )
                    self.assertIsNone(
                        restarted.ledger.get(f"setup-{outcome}")["wallet_id"]
                    )
                    self.assertEqual(
                        restarted.ledger.get(f"setup-{outcome}")["idempotency_key"],
                        setup_key,
                    )
                    expected_count = 2 if outcome == "ambiguous" else 1
                    self.assertEqual(provider.create_count, expected_count)

    def test_unknown_with_no_match_retries_same_key_only_inside_window(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "setup.json"
            now = [1000.0]
            provider = FakePrivy()
            manager = SetupManager(SetupLedger(path), provider, now=lambda: now[0])
            create_wallet = provider.create_wallet
            failed_keys = []
            retry_keys = []

            def fail_before_acceptance(**kwargs):
                failed_keys.append(kwargs["idempotency_key"])
                raise TimeoutError("simulated pre-acceptance failure")

            def retry_with_recorded_key(**kwargs):
                retry_keys.append(kwargs["idempotency_key"])
                return create_wallet(**kwargs)

            provider.create_wallet = fail_before_acceptance
            with self.assertRaises(TimeoutError):
                manager.create("setup-a", "owner-a", "agent-a")
            setup_key = manager.ledger.get("setup-a")["idempotency_key"]

            provider.create_wallet = retry_with_recorded_key
            now[0] += 60
            restarted = SetupManager(SetupLedger(path), provider, now=lambda: now[0])
            self.assertEqual(restarted.resume("setup-a"), "CONFIRMED")
            self.assertEqual(provider.create_count, 1)
            self.assertEqual(failed_keys, [setup_key])
            self.assertEqual(retry_keys, [setup_key])
            self.assertEqual(
                restarted.ledger.get("setup-a")["idempotency_key"], setup_key
            )

            missing = FakePrivy()
            missing_create_wallet = missing.create_wallet
            failed = SetupManager(
                SetupLedger(Path(directory) / "expired.json"),
                missing,
                now=lambda: now[0],
            )
            missing.create_wallet = fail_before_acceptance
            with self.assertRaises(TimeoutError):
                failed.create("setup-b", "owner-a", "agent-b")
            original = failed.ledger.get("setup-b")
            now[0] += 24 * 60 * 60 + 1
            missing.create_wallet = missing_create_wallet
            expired = SetupManager(
                SetupLedger(Path(directory) / "expired.json"),
                missing,
                now=lambda: now[0],
            )
            self.assertEqual(expired.resume("setup-b"), "UNKNOWN")
            self.assertEqual(missing.create_count, 0)
            self.assertEqual(
                expired.ledger.get("setup-b")["idempotency_key"],
                original["idempotency_key"],
            )

    def test_fake_provider_denies_a_signer_on_another_agents_wallet(self) -> None:
        provider = FakePrivy()
        wallet_a = self.create_wallet(provider, "setup-a", "owner-a", "agent-a")
        wallet_b = self.create_wallet(provider, "setup-b", "owner-a", "agent-b")
        wallet_c = self.create_wallet(provider, "setup-c", "owner-b", "agent-c")
        provider.add_signer(wallet_a, "signer-a")

        self.assertEqual(
            provider.sign(wallet_a, "signer-a", provider.safe_test_payload(wallet_a)),
            "ALLOW_FAKE_ONLY",
        )
        result = provider.sign(wallet_b, "signer-a", provider.safe_test_payload(wallet_b))
        owner_result = provider.sign(
            wallet_c, "signer-a", provider.safe_test_payload(wallet_c)
        )

        self.assertEqual(result, "DENY_SIGNER_NOT_ATTACHED")
        self.assertEqual(owner_result, "DENY_SIGNER_NOT_ATTACHED")
        self.assertEqual(
            [attempt["wallet_id"] for attempt in provider.sign_attempts[-2:]],
            [wallet_b, wallet_c],
        )
        self.assertEqual(
            [attempt["signer_id"] for attempt in provider.sign_attempts[-2:]],
            ["signer-a", "signer-a"],
        )

    def test_removal_preserves_owner_and_pending_record_and_leaves_other_agent_active(self) -> None:
        provider = FakePrivy()
        wallet_a = self.create_wallet(provider, "setup-a", "owner-a", "agent-a")
        wallet_b = self.create_wallet(provider, "setup-b", "owner-a", "agent-b")
        provider.add_signer(wallet_a, "signer-a")
        provider.add_signer(wallet_b, "signer-b")
        provider.add_pending_record(wallet_a, "pending-a")

        provider.remove_signer(wallet_a, "signer-a")

        self.assertEqual(
            provider.sign(wallet_a, "signer-a", provider.safe_test_payload(wallet_a)),
            "DENY_SIGNER_NOT_ATTACHED",
        )
        self.assertEqual(
            provider.sign(wallet_b, "signer-b", provider.safe_test_payload(wallet_b)),
            "ALLOW_FAKE_ONLY",
        )
        self.assertTrue(provider.owner_access(wallet_a, "owner-a"))
        self.assertEqual(provider.pending_records(wallet_a), ["pending-a"])
        self.assertNotIn("signer-a", provider.wallets[wallet_a]["signers"])

    def create_wallet(
        self, provider: FakePrivy, setup_id: str, owner_id: str, agent_id: str
    ) -> str:
        response = provider.create_wallet(
            idempotency_key=setup_id,
            request={
                "owner_id": owner_id,
                "agent_id": agent_id,
                "network_id": 10143,
                "external_id": f"edgeos_{setup_id}",
            },
        )
        if response is None:
            self.fail("fake wallet creation did not return a wallet")
        return response["wallet_id"]


if __name__ == "__main__":
    unittest.main()
