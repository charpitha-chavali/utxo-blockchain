from wallet import Wallet
from blockchain import Blockchain, Transaction, TxInput, TxOutput

bc = Blockchain()
alice = Wallet("alice")
bob = Wallet("bob")
miner = Wallet("miner")

print("Mining genesis reward to alice...")
bc.mine_pending_transactions(alice.address)
print("Alice balance:", bc.get_balance(alice.address))

print("\nAlice sends 10 to Bob")
tx = bc.create_transaction(alice, bob.address, 10)
ok, msg = bc.submit_transaction(tx)
print("submit:", ok, msg)

print("\nAttempt double-spend: reuse same input in a second tx")
forged = Transaction(inputs=[TxInput(txid=tx.inputs[0].txid, index=tx.inputs[0].index,
                                      signature=tx.inputs[0].signature, pubkey=tx.inputs[0].pubkey)],
                      outputs=[TxOutput(amount=10, address=miner.address)])
ok2, msg2 = bc.submit_transaction(forged)
print("double-spend submit result (should fail):", ok2, msg2)

print("\nAttempt forged spend: bob tries to spend alice's coin without her key")
try:
    fake_tx = bc.create_transaction(bob, miner.address, 5)
except ValueError as e:
    print("Expected failure (bob has no balance yet):", e)

print("\nMining block with alice->bob tx...")
block = bc.mine_pending_transactions(miner.address)
print("Block mined:", block.hash[:16], "txs:", len(block.transactions))
print("Alice balance:", bc.get_balance(alice.address))
print("Bob balance:", bc.get_balance(bob.address))
print("Miner balance:", bc.get_balance(miner.address))

valid, msg = bc.is_chain_valid()
print("\nChain valid?", valid, msg)

print("\nNow tamper with a mined block's output amount directly and re-validate:")
bc.chain[-1].transactions[1].outputs[0].amount = 99999
valid, msg = bc.is_chain_valid()
print("Chain valid after tampering (should be False):", valid, msg)
