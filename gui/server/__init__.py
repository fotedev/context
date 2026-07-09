"""FastAPI server package for the context aggregator browser extension.

Wraps the existing ``core/`` modules directly — no subprocess, no duplicated
logic. Binds loopback only and uses a copy-paste pairing-code auth flow so it
works in Codespaces/GitPod without a Native Messaging dependency.
"""
