"""
gui.py
------
Simple desktop GUI (Tkinter, no extra install needed) for the UTXO
blockchain in blockchain.py / wallet.py.

Features:
  - Create wallets (each gets a keypair + address)
  - Check balance of any wallet
  - Send coins from one wallet to an address (signed, validated,
    rejected automatically if it would double-spend)
  - Mine pending transactions into a block (miner gets the block reward)
  - View the chain / mempool / UTXO set for transparency

Run with:  python3 gui.py
"""

import tkinter as tk
from tkinter import ttk, messagebox
import json

from wallet import Wallet
from blockchain import Blockchain, MINING_REWARD


class BlockchainGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("UTXO Blockchain Wallet")
        self.root.geometry("780x600")

        self.bc = Blockchain()
        self.wallets = {}   # name -> Wallet

        self._build_layout()
        self._refresh_wallet_dropdowns()
        self._log("Blockchain initialized. Genesis block created.")

    # ------------------------------------------------------------------
    def _build_layout(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)

        self.tab_wallet = ttk.Frame(notebook)
        self.tab_send = ttk.Frame(notebook)
        self.tab_mine = ttk.Frame(notebook)
        self.tab_explorer = ttk.Frame(notebook)

        notebook.add(self.tab_wallet, text="Wallets / Balance")
        notebook.add(self.tab_send, text="Send")
        notebook.add(self.tab_mine, text="Mine")
        notebook.add(self.tab_explorer, text="Chain Explorer")

        self._build_wallet_tab()
        self._build_send_tab()
        self._build_mine_tab()
        self._build_explorer_tab()

        # shared log box at the bottom
        log_frame = ttk.LabelFrame(self.root, text="Activity Log")
        log_frame.pack(fill="both", expand=False, padx=8, pady=(0, 8))
        self.log_box = tk.Text(log_frame, height=8, state="disabled", wrap="word")
        self.log_box.pack(fill="both", expand=True)

    def _log(self, msg):
        self.log_box.config(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    # -- Wallet tab -------------------------------------------------------
    def _build_wallet_tab(self):
        f = self.tab_wallet

        create_frame = ttk.LabelFrame(f, text="Create Wallet")
        create_frame.pack(fill="x", padx=10, pady=10)
        ttk.Label(create_frame, text="Name:").pack(side="left", padx=5, pady=5)
        self.new_wallet_name = ttk.Entry(create_frame, width=20)
        self.new_wallet_name.pack(side="left", padx=5)
        ttk.Button(create_frame, text="Create Wallet", command=self.create_wallet).pack(side="left", padx=5)

        balance_frame = ttk.LabelFrame(f, text="Check Balance")
        balance_frame.pack(fill="x", padx=10, pady=10)
        ttk.Label(balance_frame, text="Wallet:").pack(side="left", padx=5, pady=5)
        self.balance_wallet_dd = ttk.Combobox(balance_frame, state="readonly", width=20)
        self.balance_wallet_dd.pack(side="left", padx=5)
        ttk.Button(balance_frame, text="Check Balance", command=self.check_balance).pack(side="left", padx=5)
        self.balance_result = ttk.Label(balance_frame, text="", font=("TkDefaultFont", 11, "bold"))
        self.balance_result.pack(side="left", padx=15)

        list_frame = ttk.LabelFrame(f, text="All Wallets")
        list_frame.pack(fill="both", expand=True, padx=10, pady=10)
        columns = ("name", "address", "balance")
        self.wallet_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=10)
        for c, w in zip(columns, (100, 450, 100)):
            self.wallet_tree.heading(c, text=c.capitalize())
            self.wallet_tree.column(c, width=w)
        self.wallet_tree.pack(fill="both", expand=True, padx=5, pady=5)
        ttk.Button(list_frame, text="Refresh", command=self._refresh_wallet_list).pack(pady=5)

    def create_wallet(self):
        name = self.new_wallet_name.get().strip()
        if not name:
            messagebox.showerror("Error", "Enter a wallet name")
            return
        if name in self.wallets:
            messagebox.showerror("Error", "Wallet name already exists")
            return
        w = Wallet(name)
        self.wallets[name] = w
        self._log(f"Created wallet '{name}' -> address {w.address}")
        self.new_wallet_name.delete(0, "end")
        self._refresh_wallet_dropdowns()
        self._refresh_wallet_list()

    def check_balance(self):
        name = self.balance_wallet_dd.get()
        if not name:
            return
        bal = self.bc.get_balance(self.wallets[name].address)
        self.balance_result.config(text=f"{bal} coins")

    def _refresh_wallet_list(self):
        for row in self.wallet_tree.get_children():
            self.wallet_tree.delete(row)
        for name, w in self.wallets.items():
            bal = self.bc.get_balance(w.address)
            self.wallet_tree.insert("", "end", values=(name, w.address, bal))

    # -- Send tab -----------------------------------------------------------
    def _build_send_tab(self):
        f = self.tab_send
        frame = ttk.LabelFrame(f, text="Send Coins")
        frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(frame, text="From wallet:").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        self.send_from_dd = ttk.Combobox(frame, state="readonly", width=25)
        self.send_from_dd.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(frame, text="To (wallet or paste address):").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        self.send_to_dd = ttk.Combobox(frame, width=45)
        self.send_to_dd.grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(frame, text="Amount:").grid(row=2, column=0, sticky="e", padx=5, pady=5)
        self.send_amount = ttk.Entry(frame, width=15)
        self.send_amount.grid(row=2, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(frame, text="Fee (optional):").grid(row=3, column=0, sticky="e", padx=5, pady=5)
        self.send_fee = ttk.Entry(frame, width=15)
        self.send_fee.insert(0, "0")
        self.send_fee.grid(row=3, column=1, sticky="w", padx=5, pady=5)

        ttk.Button(frame, text="Send", command=self.send_coins).grid(row=4, column=1, sticky="w", padx=5, pady=10)

        mempool_frame = ttk.LabelFrame(f, text="Pending Transactions (Mempool)")
        mempool_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.mempool_box = tk.Text(mempool_frame, height=12, state="disabled")
        self.mempool_box.pack(fill="both", expand=True, padx=5, pady=5)

    def send_coins(self):
        from_name = self.send_from_dd.get()
        to_val = self.send_to_dd.get().strip()
        if not from_name or not to_val:
            messagebox.showerror("Error", "Select sender and recipient")
            return
        try:
            amount = float(self.send_amount.get())
            fee = float(self.send_fee.get() or 0)
        except ValueError:
            messagebox.showerror("Error", "Amount/fee must be numbers")
            return

        sender = self.wallets[from_name]
        # 'to' can be a wallet name from the dropdown or a raw pasted address
        recipient_address = self.wallets[to_val].address if to_val in self.wallets else to_val

        try:
            tx = self.bc.create_transaction(sender, recipient_address, amount, fee)
        except ValueError as e:
            messagebox.showerror("Transaction failed", str(e))
            self._log(f"FAILED: {e}")
            return

        ok, msg = self.bc.submit_transaction(tx)
        if ok:
            self._log(f"Tx {tx.txid[:10]}... {from_name} -> {to_val} amount={amount} fee={fee}: {msg}")
        else:
            messagebox.showerror("Rejected (double-spend protection)", msg)
            self._log(f"REJECTED tx {tx.txid[:10]}...: {msg}")

        self._refresh_mempool()
        self._refresh_wallet_list()

    def _refresh_mempool(self):
        self.mempool_box.config(state="normal")
        self.mempool_box.delete("1.0", "end")
        if not self.bc.mempool:
            self.mempool_box.insert("end", "(empty)")
        for txid, tx in self.bc.mempool.items():
            self.mempool_box.insert("end", f"txid: {txid}\n")
            for o in tx.outputs:
                self.mempool_box.insert("end", f"   -> {o.amount} to {o.address}\n")
            self.mempool_box.insert("end", "\n")
        self.mempool_box.config(state="disabled")

    # -- Mine tab -------------------------------------------------------
    def _build_mine_tab(self):
        f = self.tab_mine
        frame = ttk.LabelFrame(f, text="Mine Pending Transactions")
        frame.pack(fill="x", padx=10, pady=10)
        ttk.Label(frame, text="Miner wallet (receives reward):").pack(side="left", padx=5, pady=10)
        self.miner_dd = ttk.Combobox(frame, state="readonly", width=20)
        self.miner_dd.pack(side="left", padx=5)
        ttk.Button(frame, text=f"Mine Block (reward {MINING_REWARD})", command=self.mine_block).pack(side="left", padx=10)

        info_frame = ttk.LabelFrame(f, text="Last Mined Block")
        info_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.mine_result_box = tk.Text(info_frame, height=14, state="disabled")
        self.mine_result_box.pack(fill="both", expand=True, padx=5, pady=5)

    def mine_block(self):
        name = self.miner_dd.get()
        if not name:
            messagebox.showerror("Error", "Select a miner wallet")
            return
        miner = self.wallets[name]
        block = self.bc.mine_pending_transactions(miner.address)
        self._log(f"Mined block #{block.index} hash={block.hash[:16]}... ({len(block.transactions)} txs) reward -> {name}")

        self.mine_result_box.config(state="normal")
        self.mine_result_box.delete("1.0", "end")
        self.mine_result_box.insert("end", f"Block #{block.index}\nHash: {block.hash}\nPrev: {block.previous_hash}\nNonce: {block.nonce}\n\n")
        for tx in block.transactions:
            kind = "COINBASE" if tx.is_coinbase else "transfer"
            self.mine_result_box.insert("end", f"[{kind}] {tx.txid[:12]}...\n")
            for o in tx.outputs:
                self.mine_result_box.insert("end", f"    -> {o.amount} to {o.address}\n")
        self.mine_result_box.config(state="disabled")

        self._refresh_mempool()
        self._refresh_wallet_list()
        self._refresh_explorer()

    # -- Explorer tab -----------------------------------------------------
    def _build_explorer_tab(self):
        f = self.tab_explorer
        ttk.Button(f, text="Refresh / Validate Chain", command=self._refresh_explorer).pack(pady=8)
        self.explorer_box = tk.Text(f, state="disabled")
        self.explorer_box.pack(fill="both", expand=True, padx=10, pady=10)

    def _refresh_explorer(self):
        valid, msg = self.bc.is_chain_valid()
        self.explorer_box.config(state="normal")
        self.explorer_box.delete("1.0", "end")
        self.explorer_box.insert("end", f"Chain validity: {valid} ({msg})\nBlocks: {len(self.bc.chain)}\n\n")
        for block in self.bc.chain:
            self.explorer_box.insert("end", f"--- Block #{block.index} ---\n")
            self.explorer_box.insert("end", f"hash: {block.hash}\nprev: {block.previous_hash}\nnonce: {block.nonce}\ntxs: {len(block.transactions)}\n\n")
        self.explorer_box.config(state="disabled")

    # -- shared dropdown refresh ----------------------------------------
    def _refresh_wallet_dropdowns(self):
        names = list(self.wallets.keys())
        for dd in (self.balance_wallet_dd, self.send_from_dd, self.send_to_dd, self.miner_dd):
            dd["values"] = names


def main():
    root = tk.Tk()
    app = BlockchainGUI(root)

    def on_wallet_change(*_):
        app._refresh_wallet_dropdowns()

    # hook refresh after every wallet creation already happens in create_wallet
    root.mainloop()


if __name__ == "__main__":
    main()
