"""Face rendering package — animated companion face engine.

Use :func:`create_renderer` to obtain a backend-appropriate renderer instance.
"""

from face.base import BaseRenderer


def create_renderer(backend: str = "pygame", style: str = "kawaii") -> BaseRenderer:
    """Factory: create a face renderer for the given backend.

    Parameters
    ----------
    backend : str
        Renderer backend to use.  Currently supported: ``"pygame"``.
    style : str
        Initial visual style (e.g. ``"kawaii"``, ``"retro"``, ``"minimal"``).

    Returns
    -------
    BaseRenderer
        A renderer instance implementing the :class:`BaseRenderer` interface.
    """
    if backend == "pygame":
        from face.renderer import FaceRenderer
        return FaceRenderer(style_name=style)
    elif backend == "web":
        raise NotImplementedError("Web renderer coming soon")
    raise ValueError(f"Unknown renderer backend: {backend}")
