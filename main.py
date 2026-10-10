# Alias para tunnel.py
import tunnel

if __name__ == "__main__":
    forwarder = tunnel.connect_ngrok()
    if forwarder:
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nTúnel encerrado.")
