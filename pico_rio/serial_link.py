import sys
import json
import select

class SerialLink:
    def __init__(self, timeout_ms: int = 10):
        self.timeout = timeout_ms
        self.poller = select.poll()
        # Register standard input (USB serial) for incoming data detection
        self.poller.register(sys.stdin, select.POLLIN)

    def poll_message(self) -> dict:
        """
        Non-blocking check for incoming NDJSON messages.
        Returns a parsed Python dictionary if a valid message arrives, otherwise None.
        """
        events = self.poller.poll(self.timeout)
        if events:
            # Data is available, safe to read without blocking forever
            line = sys.stdin.readline().strip()
            if line:
                try:
                    return json.loads(line)
                except ValueError:
                    self.send_error("Invalid JSON", raw=line[:20])
        return None

    def send_message(self, payload: dict):
        """
        Encodes a dictionary to JSON and sends it over USB serial with a newline.
        """
        try:
            print(json.dumps(payload))
        except Exception as e:
            # Fallback if dictionary contains un-serializable objects (e.g., bytes)
            print(json.dumps({"status": "error", "details": f"JSON encode error: {e}"}))

    def send_ack(self):
        """Convenience method to acknowledge chunk receipt."""
        self.send_message({"status": "ack"})

    def send_error(self, message: str, **kwargs):
        """Convenience method to send formatted error messages."""
        payload = {"status": "error", "details": message}
        payload.update(kwargs)
        self.send_message(payload)