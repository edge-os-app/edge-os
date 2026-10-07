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
