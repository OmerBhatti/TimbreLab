from __future__ import annotations

import importlib.util
import sys
from types import ModuleType


def provide_xformers_import_stub() -> None:
    """Let AudioCraft use its native PyTorch attention path without xformers.

    AudioCraft 1.3 imports ``xformers.ops`` unconditionally even though its
    default inference backend is PyTorch. xformers has no supported Apple
    Silicon wheel, so a tiny import shim is sufficient for the native path.
    """
    if importlib.util.find_spec("xformers") is not None:
        return

    import torch

    package = ModuleType("xformers")
    ops = ModuleType("xformers.ops")
    ops.unbind = torch.unbind

    class LowerTriangularMask:
        pass

    def memory_efficient_attention(*_args, **_kwargs):
        raise RuntimeError(
            "xformers attention is unavailable on this device; use AudioCraft's torch backend"
        )

    ops.LowerTriangularMask = LowerTriangularMask
    ops.memory_efficient_attention = memory_efficient_attention
    package.ops = ops
    sys.modules["xformers"] = package
    sys.modules["xformers.ops"] = ops


def enable_mps_compatibility() -> None:
    """Apply the upstream AudioCraft MPS inference fixes at runtime.

    AudioCraft 1.3 enables unsupported MPS autocast contexts and runs EnCodec
    operations that produce invalid output on Metal. Keep the language model
    accelerated on MPS while routing the codec through CPU.
    """
    from audiocraft.models.encodec import EncodecModel
    from audiocraft.utils.autocast import TorchAutocast

    if getattr(TorchAutocast, "_audio_playground_mps_patch", False):
        return

    original_autocast_init = TorchAutocast.__init__

    def autocast_init(self, enabled, *args, **kwargs):
        if kwargs.get("device_type") == "mps":
            enabled = False
        original_autocast_init(self, enabled, *args, **kwargs)

    TorchAutocast.__init__ = autocast_init
    TorchAutocast._audio_playground_mps_patch = True

    original_encode = EncodecModel.encode
    original_decode = EncodecModel.decode

    def encode(self, audio):
        original_device = audio.device
        model_device = next(self.encoder.parameters()).device
        codes, scale = original_encode(self, audio.to(model_device))
        return codes.to(original_device), scale

    def decode(self, codes, scale=None):
        original_device = codes.device
        model_device = next(self.decoder.parameters()).device
        if scale is not None:
            scale = scale.to(model_device)
        audio = original_decode(self, codes.to(model_device), scale)
        return audio.to(original_device)

    EncodecModel.encode = encode
    EncodecModel.decode = decode
