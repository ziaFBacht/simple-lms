"""Helper kecil yang dipakai berulang kali di api.py."""
from ninja.errors import HttpError


def get_object_or_404(model, **kwargs):
    """Ambil satu object dari database, atau raise HttpError 404."""
    try:
        return model.objects.get(**kwargs)
    except model.DoesNotExist:
        raise HttpError(404, f"{model.__name__} tidak ditemukan")