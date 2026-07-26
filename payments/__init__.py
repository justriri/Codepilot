"""
x402 payment layer for the CodePilot Agent Interface API.

Gates the paid verification endpoints (server/agent_interface.py) behind
an x402 'exact' payment challenge on X Layer, using the official x402
Python SDK (https://github.com/coinbase/x402). See docs/X402_PAYMENTS.md
for the full setup, deployment, and testing guide.
"""
