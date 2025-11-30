#!/usr/bin/env python3
"""
BSV Wallet - FINAL ENHANCED VERSION
Features:
- Send MAX
- Send Data (OP_RETURN)
- Switch Wallets (Multi-User)
- Address Details (Hex/Script)
- WhatsOnChain Data & TAAL Broadcasting
"""

import requests
import json
import qrcode
import sys
from decimal import Decimal, getcontext

# Set decimal precision
getcontext().prec = 8

# ==========================================================
# DEPENDENCY CHECK
# ==========================================================
try:
    from bsvlib import Key, Wallet as BsvWallet
    from bsvlib.constants import Chain
    from bsvlib.script import Script
    BSVLIB_AVAILABLE = True
except ImportError:
    print("CRITICAL ERROR: bsvlib not found.")
    print("Please run: pip install bsvlib==0.10.0")
    sys.exit(1)

# ==========================================================
# CONFIGURATION
# ==========================================================
WOC_BASE = "https://api.whatsonchain.com/v1/bsv/main"
TAAL_URL = "https://api.taal.com/api/v1/broadcast"

# TAAL Keys
TAAL_KEYS = [
    "mainnet_3b1bf0f0d550275f1ba8676c1e224fc1",
    "mainnet_7bf481e9cd46f48c44a71de1b326bea4"
]

# ==========================================================
# UTILITIES
# ==========================================================

class Colors:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    PURPLE = "\033[95m"
    CYAN = "\033[96m"
    END = "\033[0m"

    @staticmethod
    def print(color, text):
        print(f"{color}{text}{Colors.END}")

class NetworkProvider:
    @staticmethod
    def get_json(endpoint):
        try:
            r = requests.get(f"{WOC_BASE}/{endpoint}", timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception:
            return None

    @staticmethod
    def get_price():
        data = NetworkProvider.get_json("exchangerate")
        if data:
            return data.get('rate', '0.00')
        return '0.00'

    @staticmethod
    def get_history(address):
        return NetworkProvider.get_json(f"address/{address}/history")

    @staticmethod
    def get_tx_details(txid):
        return NetworkProvider.get_json(f"tx/hash/{txid}")

    @staticmethod
    def get_chain_info():
        return NetworkProvider.get_json("chain/info")

    @staticmethod
    def broadcast(raw_hex):
        # 1. Try TAAL
        Colors.print(Colors.YELLOW, "Broadcasting via TAAL...")
        for key in TAAL_KEYS:
            try:
                headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
                r = requests.post(TAAL_URL, json={"rawTx": raw_hex}, headers=headers, timeout=10)
                if r.status_code == 200:
                    try:
                        resp = r.json()
                        if isinstance(resp, dict): return resp.get('txid', resp.get('result'))
                        return str(resp)
                    except: return r.text
            except: continue

        # 2. Fallback to WhatsOnChain
        Colors.print(Colors.YELLOW, "TAAL failed. Trying WhatsOnChain...")
        try:
            r = requests.post(f"{WOC_BASE}/tx/raw", json={"txhex": raw_hex}, timeout=15)
            r.raise_for_status()
            return r.text.replace('"', '').strip()
        except Exception as e:
            Colors.print(Colors.RED, f"Broadcast Failed: {e}")
            return None

# ==========================================================
# WALLET APP
# ==========================================================

class WalletApp:
    def __init__(self, private_key_wif):
        try:
            self.key = Key(private_key_wif)
            self.address = self.key.address()
            self.bsv_wallet = BsvWallet([private_key_wif], chain=Chain.MAIN)
            self.network = NetworkProvider()
        except Exception as e:
            Colors.print(Colors.RED, f"Key Error: {e}")
            raise e

    def get_balance_sats(self):
        """Returns confirmed + unconfirmed balance in satoshis"""
        return self.bsv_wallet.get_balance(refresh=True)

    def show_status(self):
        print("\n" + "-"*40)
        Colors.print(Colors.GREEN, f"Wallet: {self.address}")
        
        try:
            bal_sats = self.get_balance_sats()
            bal_bsv = Decimal(bal_sats) / 100_000_000
            price = self.network.get_price()
            usd_val = bal_bsv * Decimal(price)
            
            print(f"Balance:   {bal_bsv:.8f} BSV")
            Colors.print(Colors.CYAN, f"USD Value:   ${usd_val:,.2f} (@ ${price}/BSV)")
        except Exception as e:
            Colors.print(Colors.RED, f"Error fetching balance: {e}")
        print("-"*40)

    def show_details(self):
        """Shows technical address details"""
        print("\n" + "="*40)
        print("ADDRESS TECHNICAL DETAILS")
        print("="*40)
        print(f"Address:    {self.address}")
        try:
            pub_hex = self.key.public_key().hex()
            print(f"Public Key: {pub_hex}")
            # Script Pub Key (P2PKH)
            script = Script(self.address)
            print(f"Script(Hex):{script.to_hex()}")
        except:
            pass
        print("="*40)

    def send_op_return(self, data_string):
        """Send a data-only transaction"""
        print("\n" + "="*40)
        Colors.print(Colors.YELLOW, "PREPARING DATA TRANSACTION (OP_RETURN)...")
        
        try:
            # Check balance for fees
            bal = self.get_balance_sats()
            if bal < 1000:
                Colors.print(Colors.RED, "Insufficient funds for fee.")
                return

            # Build Data Transaction
            # We pass an empty outputs list because we aren't sending BSV to anyone
            # We pass 'pushdatas' to create the OP_RETURN output
            tx = self.bsv_wallet.create_transaction(
                outputs=[], 
                pushdatas=[data_string],
                combine=True # Best practice for chaining
            )
            
            raw_hex = tx.hex()
            
            print("="*40)
            print(f"Data:    {data_string}")
            print(f"Size:    {len(raw_hex)//2} bytes")
            print(f"Fee:     ~{len(raw_hex)//2 * 0.5} sats (Estimated)")
            print("="*40)
            
            confirm = input("Broadcast Data? (yes/no): ").lower()
            if confirm == "yes":
                txid = self.network.broadcast(raw_hex)
                if txid and len(txid) > 20:
                    Colors.print(Colors.GREEN, "\n✅ Data Written Successfully!")
                    print(f"TXID: {txid}")
                    print(f"Link: https://whatsonchain.com/tx/{txid}")
                else:
                    Colors.print(Colors.RED, "Broadcast failed.")
            else:
                Colors.print(Colors.YELLOW, "Cancelled.")

        except Exception as e:
            Colors.print(Colors.RED, f"Data Error: {e}")

    def build_and_send(self, to_address, amount_str):
        print("\n" + "="*40)
        Colors.print(Colors.YELLOW, "PREPARING TRANSACTION...")
        
        try:
            total_sats = self.get_balance_sats()
            fee_estimate = 500 
            
            if amount_str.lower() in ['max', 'all']:
                send_sats = total_sats - fee_estimate
                if send_sats <= 0:
                    Colors.print(Colors.RED, "Balance too low for fee.")
                    return
                print(f"Calculating MAX send: {Decimal(send_sats)/100_000_000} BSV")
            else:
                send_sats = int(Decimal(amount_str) * 100_000_000)

            if send_sats > total_sats:
                Colors.print(Colors.RED, f"Insufficient funds.")
                return

            # Create Transaction
            tx = self.bsv_wallet.create_transaction(
                outputs=[(to_address, send_sats)],
                fee=fee_estimate if amount_str.lower() in ['max', 'all'] else None
            )
            
            raw_hex = tx.hex()
            
            print("="*40)
            print(f"To:      {to_address}")
            print(f"Amount:  {Decimal(send_sats)/100_000_000} BSV")
            print(f"Size:    {len(raw_hex)//2} bytes")
            print("="*40)

            confirm = input("Broadcast? (yes/no): ").lower()
            if confirm == "yes":
                txid = self.network.broadcast(raw_hex)
                if txid and len(txid) > 20:
                    Colors.print(Colors.GREEN, "\n✅ Transaction Successful!")
                    print(f"TXID: {txid}")
                    print(f"Link: https://whatsonchain.com/tx/{txid}")
                else:
                    Colors.print(Colors.RED, "Broadcast failed.")
            else:
                Colors.print(Colors.YELLOW, "Cancelled.")

        except Exception as e:
            Colors.print(Colors.RED, f"Transaction Failed: {e}")

# ==========================================================
# MAIN MENU
# ==========================================================

def main():
    print(r"""
  ____  ______      __  _       __     _  _      _   
 |  _ \/ ___\ \    / / | |     / /_   | || | ___| |_ 
 | |_) \___ \\ \  / /  | | /\ / / _ \ | || |/ _ \ __|
 |  _ < ___) |\ \/ /   | |/  / / (_) || || |  __/ |_ 
 |_| \_\____/  \__/    |___/\___\___/ |_||_|\___|\__|
    """)
    Colors.print(Colors.PURPLE, "     BSV Wallet - Enhanced Edition")

    # Main Application Loop (Allows switching wallets)
    while True:
        try:
            pk = input("\nEnter Private Key (WIF) or 'q' to quit: ").strip()
            if pk.lower() in ['q', 'quit', 'exit']:
                sys.exit(0)
            if not pk: continue
            
            wallet = WalletApp(pk)
            Colors.print(Colors.GREEN, "\n✅ Wallet Loaded Successfully")
            
            # Inner Menu Loop
            while True:
                print("\n" + "="*50)
                print("1. Wallet Status (Balance)")
                print("2. Send BSV (Standard)")
                print("3. Send Data (OP_RETURN)")
                print("4. Transaction History")
                print("5. UTXO List")
                print("6. Address Technical Details")
                print("7. Generate QR Code")
                print("8. Switch Wallet")
                print("9. Exit")
                print("="*50)
                
                choice = input("Select Option: ")

                if choice == "1":
                    wallet.show_status()

                elif choice == "2":
                    dest = input("Recipient Address: ").strip()
                    print("Type 'MAX' to send entire balance.")
                    amt = input("Amount BSV: ").strip()
                    try:
                        wallet.build_and_send(dest, amt)
                    except ValueError:
                        Colors.print(Colors.RED, "Invalid amount format")

                elif choice == "3":
                    data = input("Enter Data to Write (Text): ").strip()
                    if data:
                        wallet.send_op_return(data)

                elif choice == "4":
                    print("\n--- Last 10 Transactions ---")
                    hist = wallet.network.get_history(wallet.address)
                    if hist:
                        for tx in reversed(hist[-10:]):
                            print(f"TX: {tx['tx_hash'][:20]}... | Height: {tx.get('height', 'Unconfirmed')}")
                    else:
                        print("No history found.")

                elif choice == "5":
                    utxos = wallet.bsv_wallet.get_unspents(refresh=True)
                    print(f"\n--- Found {len(utxos)} UTXOs ---")
                    for u in utxos:
                        val_bsv = u.satoshis / 100_000_000
                        print(f"{val_bsv:.8f} BSV | {u.txid[:15]}...")

                elif choice == "6":
                    wallet.show_details()

                elif choice == "7":
                    try:
                        img = qrcode.make(wallet.address)
                        fn = f"bsv_{wallet.address[:6]}.png"
                        img.save(fn)
                        Colors.print(Colors.GREEN, f"QR Code saved to {fn}")
                    except Exception as e:
                        print(f"Error: {e}")

                elif choice == "8":
                    Colors.print(Colors.YELLOW, "\nSwitching Wallet...")
                    break # Breaks inner loop, returns to key input

                elif choice == "9":
                    print("Goodbye!")
                    sys.exit(0)

        except Exception as e:
            Colors.print(Colors.RED, f"Error loading wallet: {e}")

if __name__ == "__main__":
    main()
