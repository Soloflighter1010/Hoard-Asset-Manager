"""The common store contract; transports, retries and download records stay shared."""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from .services import lib, dl, wish


class UnsupportedOperation(ValueError):
    """A store explicitly does not offer this operation through Hoard."""


@dataclass(frozen=True)
class Adapter:
    """One store's identity and supported operations, independent of browser ownership.

    A caller supplies the signed-in context, configuration and progress callback.
    File operations use the shared download engine's selection and report shapes,
    so listing/checking cannot accidentally write a download to disk.
    """

    key: str
    label: str
    login: str
    referer: str
    order: int
    downloads: bool = True
    wishlists: bool = True
    saved_pages: bool = True
    requests_per_minute: int | None = None

    @property
    def capabilities(self) -> dict[str, bool]:
        """Explicit feature flags for callers; an unsupported operation never silently succeeds."""
        return {"library": True, "quick": True, "wishlists": self.wishlists,
                "saved_pages": self.saved_pages, "list_files": self.downloads,
                "download_file": self.downloads, "check_updates": self.downloads}

    def limits(self, cfg: dict) -> dict:
        """The configured request spacing and the store's published upper bound, if known."""
        return {"delay_seconds": max(0.0, float(cfg.get("request_delay", 1.0))),
                "requests_per_minute": self.requests_per_minute}

    def _call(self, operation: str, function, *args, result_problem=None):
        """Keep a bounded, account-free health record for each attempted store operation. The record is only a note:
        one that can't be kept (a full disk, say) never costs the read its result, nor hides the store's own error."""
        from . import health

        def note(problem: str) -> None:
            """Keep how this operation went: a note that can't be kept is said in the log, never raised."""
            try:
                health.record(self.key, operation, problem)
            except Exception as e:  # noqa: BLE001 (a note, never the read)
                print(f"Couldn't note how {self.label} went: {type(e).__name__}", flush=True)
        try:
            result = function(*args)
        except Exception as error:
            note(health.classify(error))
            raise
        note(result_problem(result) if result_problem else "")
        return result

    def read_library(self, ctx, cfg: dict, progress, *, quick: bool = False) -> list[dict]:
        """Read purchases in full, or only the start; preserve reader hand-back fields in cfg."""
        if quick:
            cfg["_quick"] = True
        return self._call("library", getattr(lib, "fetch_" + self.key), ctx, cfg, progress,
                          result_problem=lambda items: "empty" if not items and cfg.get("_previous_count", 0) > 0 else
                          "partial" if cfg.get("_unread_payhip_shops") else "")

    def read_wishlists(self, ctx, cfg: dict, progress, *, quick: bool = False) -> list[dict]:
        """Read supported wishlists, preserving each list's partial marker during Quick refresh."""
        if not self.wishlists:
            raise UnsupportedOperation(f"{self.label} wishlists aren't supported")
        if quick:
            cfg["_quick"] = True
        return self._call("wishlists", getattr(wish, "read_" + self.key), ctx, cfg, progress)

    def transfer(self, cfg: dict, root, args, report) -> None:
        """Run the shared engine's chosen-file selection in download, list or check mode."""
        if not self.downloads:
            raise UnsupportedOperation(f"{self.label} lists purchases; download from its website")
        operation = "list_files" if getattr(args, "listing", False) else "check_updates" if args.dry_run else "download_file"
        failed = len(report.failed)
        from . import health
        try:
            getattr(dl, "sync_" + self.key)(cfg, root, args, report)
        except Exception as error:
            health.record(self.key, operation, health.classify(error))
            raise
        health.record(self.key, operation, "partial" if len(report.failed) > failed else "")

    def list_files(self, cfg: dict, root, args, report) -> None:
        """List files using the normal product selection, without changing download records."""
        self.transfer(cfg, root, SimpleNamespace(**{**vars(args), "dry_run": True, "listing": True}), report)

    def check_updates(self, cfg: dict, root, args, report) -> None:
        """Compare offered files with download records, without downloading anything."""
        self.transfer(cfg, root, SimpleNamespace(**{**vars(args), "dry_run": True, "listing": False}), report)

    def download_file(self, cfg: dict, root, args, report) -> None:
        """Download the caller's selected files through the common retry and record machinery."""
        self.transfer(cfg, root, SimpleNamespace(**{**vars(args), "dry_run": False, "listing": False}), report)

    def read_saved(self, page, cfg: dict, prep: dict) -> list[dict]:
        """Read an already isolated saved library page using this store's parser."""
        if not self.saved_pages:
            raise UnsupportedOperation(f"{self.label} saved library pages aren't supported")
        from . import modules
        return modules()[self.key].read_saved(page, cfg, prep)

    def saved_wishlist(self, page, kind: str, url: str, html: str, name: str) -> list[dict]:
        """Read an already isolated saved wishlist page, without opening a network connection."""
        if not self.wishlists:
            raise UnsupportedOperation(f"{self.label} wishlists aren't supported")
        from . import modules
        return modules()[self.key].saved_wishlist(page, kind, url, html, name)

    def tags(self, page) -> list:
        """Return raw creator tags for common normalization, or none where the store has no tags."""
        from . import modules
        reader = getattr(modules()[self.key], "read_tags", None)
        return reader(page) if reader else []
