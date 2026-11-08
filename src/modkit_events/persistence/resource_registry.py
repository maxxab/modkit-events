"""Local permanent domain-stop primitive; transport integration is not implemented.

Use the canonical module once per process. Reloading, duplicate module loading,
private mutation and inheriting a live domain across fork are unsupported.
"""

from threading import Lock as _Lock


class DomainStopReceipt:
    """Payload-free, preissued identity attesting that this domain is stopped."""

    __slots__ = ("__domain",)

    def __new__(cls):
        raise TypeError("DomainStopReceipt is issued internally")

    def __init_subclass__(cls, **kwargs):
        raise TypeError("DomainStopReceipt cannot be subclassed")

    def __setattr__(self, name, value):
        raise AttributeError("DomainStopReceipt is immutable")

    def __delattr__(self, name):
        raise AttributeError("DomainStopReceipt is immutable")

    @property
    def domain(self):
        """Return the exact issuing domain, not a resource or outcome."""
        return self.__domain

    def __repr__(self):
        return "<DomainStopReceipt>"

    def __copy__(self):
        raise TypeError("DomainStopReceipt cannot be copied")

    def __deepcopy__(self, memo):
        raise TypeError("DomainStopReceipt cannot be copied")

    def __reduce_ex__(self, protocol):
        raise TypeError("DomainStopReceipt cannot be serialized")


class ResourceDomain:
    """One permanent stop latch, independent of any registry/ledger mutex."""

    __slots__ = ("__stop_latch", "__receipt")

    def __new__(cls):
        raise TypeError("use resource_domain()")

    def __init_subclass__(cls, **kwargs):
        raise TypeError("ResourceDomain cannot be subclassed")

    def __setattr__(self, name, value):
        raise AttributeError("ResourceDomain is immutable")

    def __delattr__(self, name):
        raise AttributeError("ResourceDomain is immutable")

    @property
    def stopped(self):
        """Observe the actual monotone latch, never a cached Boolean."""
        return self.__stop_latch.locked()

    def trip(self):
        """Stop permanently; an already-held latch is already stopped.

        The ordinary Lock primitive must complete. A lost/interrupted return
        supplies no receipt and does not promise further Python execution.
        """
        self.__stop_latch.acquire(blocking=False)
        return self.__receipt

    def __repr__(self):
        return "<ResourceDomain>"

    def __copy__(self):
        raise TypeError("ResourceDomain cannot be copied")

    def __deepcopy__(self, memo):
        raise TypeError("ResourceDomain cannot be copied")

    def __reduce_ex__(self, protocol):
        raise TypeError("ResourceDomain cannot be serialized")


# Import-time detached bootstrap. No public factory can issue another instance.
# Objects are fully initialized before the canonical accessor becomes available.
_domain = object.__new__(ResourceDomain)
_receipt = object.__new__(DomainStopReceipt)
object.__setattr__(_domain, "_ResourceDomain__stop_latch", _Lock())
object.__setattr__(_receipt, "_DomainStopReceipt__domain", _domain)
object.__setattr__(_domain, "_ResourceDomain__receipt", _receipt)
del _receipt, _Lock


def resource_domain():
    """Return the sole canonical process domain; no reset or replacement API."""
    return _domain
