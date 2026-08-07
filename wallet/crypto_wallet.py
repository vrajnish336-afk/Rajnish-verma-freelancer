import os
from dotenv import load_dotenv

from payment_states import PAYMENT_UNKNOWN

load_dotenv()


class CentralWalletManager:
    def __init__(self):
        self.private_key = os.getenv("PRIVATE_KEY", "0x0000000000000000000000000000000000000000000000000000000000000000")
        self.rpc_url = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
        self.agent_address = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"
        self.personal_wallet = os.getenv("PERSONAL_WALLET_ADDRESS", "")

    def get_status(self):
        print(f"🏦 Treasury Address: {self.agent_address}")
        print(f"🌐 Base RPC Network: {self.rpc_url}")

    def execute_onchain_sweep(self, amount_usdc: float):
        """
        On-chain USDC sweep requires real Web3 integration.
        Does NOT fabricate transaction hashes or confirm payments.
        Returns None until a verified on-chain transaction exists.
        """
        print(f"⚠️ [Web3 Engine] On-chain sweep unavailable — no verified transaction.")
        print(f"   Requested amount: ${amount_usdc} USDC")
        print(f"   Payment status: {PAYMENT_UNKNOWN}")
        return None
