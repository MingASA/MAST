from dataclasses import dataclass,asdict
import hashlib
import json
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey,Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
from cryptography.exceptions import InvalidSignature


def canonical(value): return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()

def digest(value): return hashlib.sha256(canonical(value)).hexdigest()


@dataclass(frozen=True)
class Decision:
    action: str
    checks: tuple[str,...]
    findings: tuple[str,...]
    public_message: str
    requested_from: str | None = None
    replacement_model: str | None = None

    @classmethod
    def parse(cls,raw):
        allowed={'pass','revise','request_evidence','escalate','reject'}
        if raw.get('action') not in allowed: raise ValueError('invalid action')
        if not isinstance(raw.get('checks'),list) or not all(isinstance(x,str) for x in raw['checks']): raise ValueError('invalid checks')
        if not isinstance(raw.get('findings'),list) or not all(isinstance(x,str) for x in raw['findings']): raise ValueError('invalid findings')
        if not isinstance(raw.get('public_message'),str): raise ValueError('invalid public message')
        replacement=raw.get('replacement_model')
        if isinstance(replacement,dict):
            replacement=replacement.get('to_model',replacement.get('new_value'))
        if replacement is not None and not isinstance(replacement,str): raise ValueError('invalid replacement model')
        return cls(raw['action'],tuple(raw['checks']),tuple(raw['findings']),raw['public_message'],raw.get('requested_from'),replacement)


@dataclass(frozen=True)
class Certificate:
    issuer: str
    version: int
    bundle_hash: str
    checks: tuple[str,...]
    findings: tuple[str,...]
    action: str
    signature: str = ''

    def payload(self):
        value=asdict(self); value.pop('signature'); return canonical(value)

    @classmethod
    def issue(cls,issuer,version,bundle,decision,key):
        unsigned=cls(issuer,version,digest(bundle),decision.checks,decision.findings,decision.action)
        return cls(issuer,version,digest(bundle),decision.checks,decision.findings,decision.action,key.sign(unsigned.payload()).hex())

    def verify(self,public_key,bundle,version):
        if self.version!=version or self.bundle_hash!=digest(bundle): return False
        try: Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)).verify(bytes.fromhex(self.signature),self.payload())
        except (InvalidSignature,ValueError): return False
        return True


def keypair():
    private=Ed25519PrivateKey.generate()
    public=private.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw).hex()
    return private,public
