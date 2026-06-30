"""
blockchain.py
-------------
A UTXO-model blockchain (same accounting model as Bitcoin).

Key ideas:

1. UTXO (Unspent Transaction Output) model:
   Nobody has a "balance" stored as a number anywhere. Instead, the chain
   just tracks a big set of "coins" (outputs) that haven't been spent yet.
   Your "balance" = sum of all unspent outputs that belong to your address.
   To spend money you must explicitly reference *which* unspent outputs
   you're consuming as inputs, and the value out (+ optional fee) must
   not exceed the value in.

2. Double-spend prevention happens at THREE layers:
   a) Signature check       -> you cannot reference/spend an output that
                                isn't yours (you can't forge ownership).
   b) Mempool reservation   -> once an unconfirmed transaction references
                                a UTXO, that UTXO is "reserved" so a second
                                conflicting transaction spending the same
                                coin is rejected before it ever gets mined.
   c) Block validation      -> when building/accepting a block, each input
                                is checked against the live UTXO set, and
                                a running "spent in this block" set is kept
                                so two transactions in the *same* block
                                can't double-spend each other either.

3. Mining reward: the first transaction in every block is a special
   "coinbase" transaction with no inputs, created by the chain itself,
   paying the miner a fixed block reward + collected transaction fees.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

from wallet import Wallet, sha256

MINING_REWARD = 50.0
DIFFICULTY = 4          # number of leading zeros required in block hash
COINBASE_SENDER = "COINBASE"


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

@dataclass
class TxInput:
    txid: str          # id of the transaction that created the output we spend
    index: int          # which output of that transaction
    signature: str = ""  # signature proving ownership (filled in when signed)
    pubkey: str = ""     # public key of the spender (so anyone can verify)

    def to_dict(self, include_sig=True):
        d = {"txid": self.txid, "index": self.index}
        if include_sig:
            d["signature"] = self.signature
            d["pubkey"] = self.pubkey
        return d


@dataclass
class TxOutput:
    amount: float
    address: str        # recipient's address

    def to_dict(self):
        return {"amount": self.amount, "address": self.address}


class Transaction:
    def __init__(self, inputs: List[TxInput], outputs: List[TxOutput], is_coinbase=False):
        self.inputs = inputs
        self.outputs = outputs
        self.is_coinbase = is_coinbase
        self.timestamp = time.time()
        self.txid = self.compute_txid()

    def signing_payload(self) -> str:
        """The data that gets signed -- inputs (without sigs) + outputs."""
        payload = {
            "inputs": [i.to_dict(include_sig=False) for i in self.inputs],
            "outputs": [o.to_dict() for o in self.outputs],
            "timestamp": self.timestamp,
        }
        return json.dumps(payload, sort_keys=True)

    def compute_txid(self) -> str:
        full = {
            "inputs": [i.to_dict() for i in self.inputs],
            "outputs": [o.to_dict() for o in self.outputs],
            "timestamp": self.timestamp,
            "coinbase": self.is_coinbase,
        }
        return sha256(json.dumps(full, sort_keys=True).encode())

    def to_dict(self):
        return {
            "txid": self.txid,
            "inputs": [i.to_dict() for i in self.inputs],
            "outputs": [o.to_dict() for o in self.outputs],
            "timestamp": self.timestamp,
            "is_coinbase": self.is_coinbase,
        }


def make_coinbase_tx(miner_address: str, reward: float) -> Transaction:
    tx = Transaction(inputs=[], outputs=[TxOutput(amount=reward, address=miner_address)],
                      is_coinbase=True)
    return tx


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------

class Block:
    def __init__(self, index: int, previous_hash: str, transactions: List[Transaction], nonce=0, timestamp=None):
        self.index = index
        self.previous_hash = previous_hash
        self.transactions = transactions
        self.nonce = nonce
        self.timestamp = timestamp or time.time()
        self.hash = self.compute_hash()

    def compute_hash(self) -> str:
        block_data = {
            "index": self.index,
            "previous_hash": self.previous_hash,
            "transactions": [t.to_dict() for t in self.transactions],
            "nonce": self.nonce,
            "timestamp": self.timestamp,
        }
        return sha256(json.dumps(block_data, sort_keys=True).encode())

    def mine(self, difficulty=DIFFICULTY):
        target = "0" * difficulty
        while not self.hash.startswith(target):
            self.nonce += 1
            self.hash = self.compute_hash()
        return self.hash


# ---------------------------------------------------------------------------
# Blockchain
# ---------------------------------------------------------------------------

class Blockchain:
    def __init__(self):
        self.chain: List[Block] = []
        # UTXO set: (txid, index) -> TxOutput
        self.utxo_set: Dict[Tuple[str, int], TxOutput] = {}
        # mempool: pending unconfirmed transactions, txid -> Transaction
        self.mempool: Dict[str, Transaction] = {}
        # which UTXOs are already "reserved" by a pending mempool tx
        # (txid, index) -> mempool txid that reserved it
        self.reserved_utxos: Dict[Tuple[str, int], str] = {}
        self._create_genesis_block()

    # -- genesis ------------------------------------------------------
    def _create_genesis_block(self):
        genesis = Block(index=0, previous_hash="0" * 64, transactions=[])
        genesis.mine(DIFFICULTY)
        self.chain.append(genesis)

    @property
    def last_block(self) -> Block:
        return self.chain[-1]

    # -- balances -------------------------------------------------------
    def get_balance(self, address: str) -> float:
        return sum(o.amount for o in self.utxo_set.values() if o.address == address)

    def get_unspent_outputs_for(self, address: str) -> List[Tuple[Tuple[str, int], TxOutput]]:
        return [(k, v) for k, v in self.utxo_set.items() if v.address == address]

    # -- creating & signing a transaction --------------------------------
    def create_transaction(self, sender_wallet: Wallet, recipient_address: str, amount: float,
                            fee: float = 0.0) -> Transaction:
        """
        Build, sign, and validate a new transaction spending sender_wallet's
        UTXOs. Raises ValueError on insufficient funds. Does NOT yet add it
        to the mempool -- call submit_transaction for that (it re-validates
        against double-spend conditions).
        """
        available = self.get_unspent_outputs_for(sender_wallet.address)
        # only consider UTXOs not already reserved by another pending tx
        available = [(k, v) for k, v in available if k not in self.reserved_utxos]

        total_needed = amount + fee
        chosen = []
        running_total = 0.0
        for key, output in available:
            chosen.append((key, output))
            running_total += output.amount
            if running_total >= total_needed:
                break

        if running_total < total_needed:
            raise ValueError(
                f"Insufficient balance: have {running_total}, need {total_needed}"
            )

        inputs = [TxInput(txid=k[0], index=k[1], pubkey=sender_wallet.public_key) for k, _ in chosen]
        outputs = [TxOutput(amount=amount, address=recipient_address)]

        change = running_total - total_needed
        if change > 1e-9:
            outputs.append(TxOutput(amount=change, address=sender_wallet.address))

        tx = Transaction(inputs=inputs, outputs=outputs)

        # sign every input with the same signature over the shared payload
        payload = tx.signing_payload()
        sig = sender_wallet.sign(payload)
        for i in tx.inputs:
            i.signature = sig

        return tx

    # -- validating a transaction -----------------------------------------
    def validate_transaction(self, tx: Transaction, utxo_view: Optional[Dict] = None,
                              spent_in_progress: Optional[set] = None) -> Tuple[bool, str]:
        """
        Validate a transaction against a given UTXO view (defaults to the
        live UTXO set). `spent_in_progress` lets a caller track UTXOs
        already consumed earlier in the same batch (e.g. same block) to
        prevent double spends *within* that batch.
        """
        if tx.is_coinbase:
            if len(tx.inputs) != 0:
                return False, "Coinbase transaction must have no inputs"
            if len(tx.outputs) != 1 or tx.outputs[0].amount > MINING_REWARD + 1e-9:
                return False, "Invalid coinbase reward amount"
            return True, "ok"

        utxo_view = utxo_view if utxo_view is not None else self.utxo_set
        spent_in_progress = spent_in_progress if spent_in_progress is not None else set()

        if not tx.inputs:
            return False, "Transaction has no inputs"

        payload = tx.signing_payload()
        total_in = 0.0
        seen_keys = set()

        for i in tx.inputs:
            key = (i.txid, i.index)

            if key in seen_keys:
                return False, "Duplicate input within the same transaction"
            seen_keys.add(key)

            # --- double-spend check #1: already spent on-chain or reserved
            if key not in utxo_view:
                return False, f"Input {key} does not exist or is already spent (double-spend attempt)"

            if key in spent_in_progress:
                return False, f"Input {key} already spent earlier in this batch (double-spend attempt)"

            output = utxo_view[key]

            # --- ownership check: signature must verify against the
            # public key, AND that public key must hash to the address
            # that actually owns the output being spent.
            from wallet import hash_pubkey_to_address
            if hash_pubkey_to_address(i.pubkey) != output.address:
                return False, "Input pubkey does not match the owner of the referenced output"

            if not Wallet.verify(i.pubkey, payload, i.signature):
                return False, "Invalid signature (forged or tampered transaction)"

            total_in += output.amount

        total_out = sum(o.amount for o in tx.outputs)
        if total_out > total_in + 1e-9:
            return False, f"Outputs ({total_out}) exceed inputs ({total_in}) -- inflation attempt"

        return True, "ok"

    # -- mempool ------------------------------------------------------------
    def submit_transaction(self, tx: Transaction) -> Tuple[bool, str]:
        """Validate and add a transaction to the mempool, reserving its inputs."""
        ok, msg = self.validate_transaction(tx)
        if not ok:
            return False, msg

        for i in tx.inputs:
            key = (i.txid, i.index)
            if key in self.reserved_utxos:
                return False, f"Input {key} already used by a pending transaction (double-spend attempt)"

        for i in tx.inputs:
            self.reserved_utxos[(i.txid, i.index)] = tx.txid

        self.mempool[tx.txid] = tx
        return True, "Transaction accepted into mempool"

    # -- mining ---------------------------------------------------------
    def mine_pending_transactions(self, miner_address: str) -> Block:
        """
        Take everything in the mempool, validate it one more time against
        the current UTXO set (in case anything changed), build a block,
        proof-of-work mine it, then apply it to the UTXO set.
        """
        coinbase = make_coinbase_tx(miner_address, MINING_REWARD)
        block_txs = [coinbase]

        spent_in_block = set()
        for txid, tx in list(self.mempool.items()):
            ok, msg = self.validate_transaction(tx, self.utxo_set, spent_in_block)
            if not ok:
                # stale/conflicting tx -- drop it from mempool
                self._release_reservations(tx)
                del self.mempool[txid]
                continue
            for i in tx.inputs:
                spent_in_block.add((i.txid, i.index))
            block_txs.append(tx)

        new_block = Block(index=len(self.chain), previous_hash=self.last_block.hash, transactions=block_txs)
        new_block.mine(DIFFICULTY)

        self._apply_block(new_block)
        return new_block

    def _release_reservations(self, tx: Transaction):
        for i in tx.inputs:
            self.reserved_utxos.pop((i.txid, i.index), None)

    def _apply_block(self, block: Block):
        for tx in block.transactions:
            # remove spent inputs from UTXO set
            for i in tx.inputs:
                self.utxo_set.pop((i.txid, i.index), None)
                self.reserved_utxos.pop((i.txid, i.index), None)
            # add new outputs to UTXO set
            for idx, o in enumerate(tx.outputs):
                self.utxo_set[(tx.txid, idx)] = o
            # remove from mempool if it was there
            self.mempool.pop(tx.txid, None)

        self.chain.append(block)

    # -- full chain validation (e.g. after receiving a chain from a peer) --
    def is_chain_valid(self) -> Tuple[bool, str]:
        rebuilt_utxo: Dict = {}
        for idx, block in enumerate(self.chain):
            if block.index != idx:
                return False, f"Block {idx} has wrong index"
            if block.hash != block.compute_hash():
                return False, f"Block {idx} hash mismatch (tampered block)"
            if idx > 0 and block.previous_hash != self.chain[idx - 1].hash:
                return False, f"Block {idx} previous_hash mismatch (broken chain)"
            if not block.hash.startswith("0" * DIFFICULTY):
                return False, f"Block {idx} does not satisfy proof-of-work"

            spent_in_block = set()
            for tx in block.transactions:
                ok, msg = self.validate_transaction(tx, rebuilt_utxo, spent_in_block)
                if not ok:
                    return False, f"Block {idx} tx {tx.txid[:8]} invalid: {msg}"
                for i in tx.inputs:
                    spent_in_block.add((i.txid, i.index))
                for k in list(rebuilt_utxo.keys()):
                    pass
                for i in tx.inputs:
                    rebuilt_utxo.pop((i.txid, i.index), None)
                for oidx, o in enumerate(tx.outputs):
                    rebuilt_utxo[(tx.txid, oidx)] = o

        return True, "Chain is valid"
