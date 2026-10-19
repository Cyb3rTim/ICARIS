"""
Load NIST SP 800-53 controls into ICARIS.

    python manage.py import_oscal_catalog
        Loads the bundled SP 800-53 Rev 5 catalog with Low/Moderate/High baselines.

    python manage.py import_oscal_catalog --catalog NIST_SP-800-53_rev5_catalog.json \\
        --profile low=..._LOW-baseline_profile.json --profile moderate=... --profile high=...
        Loads an OSCAL catalog and baseline profiles you downloaded from
        https://github.com/usnistgov/oscal-content (use this to pick up a newer release).

    Add --write-bundle to refresh the bundled copy from the files given.
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ato import catalog as oscal
from ato.services import import_catalog


class Command(BaseCommand):
    help = "Import NIST SP 800-53 controls and baselines (bundled, or from OSCAL JSON files)."

    def add_arguments(self, parser):
        parser.add_argument("--catalog", type=Path, help="Path to an OSCAL catalog JSON file")
        parser.add_argument(
            "--profile", action="append", default=[], metavar="LEVEL=PATH",
            help="Baseline profile, e.g. moderate=NIST_SP-800-53_rev5_MODERATE-baseline_profile.json",
        )
        parser.add_argument("--write-bundle", action="store_true", help="Save the parsed result as the bundled catalog")

    def handle(self, *args, **options):
        if options["catalog"]:
            data = oscal.parse_catalog(oscal.load_json(options["catalog"]))
            baselines = {}
            for spec in options["profile"]:
                level, sep, path = spec.partition("=")
                if not sep or level not in ("low", "moderate", "high"):
                    raise CommandError(f"--profile must look like moderate=path.json (got {spec!r})")
                baselines[level] = oscal.parse_profile_ids(oscal.load_json(Path(path)))
            oscal.apply_baselines(data, baselines)
            if options["write_bundle"]:
                oscal.write_bundle(data)
                self.stdout.write(f"Bundled catalog written to {oscal.BUNDLED_CATALOG}")
        else:
            if options["profile"] or options["write_bundle"]:
                raise CommandError("--profile and --write-bundle require --catalog")
            data = oscal.load_bundled()

        result = import_catalog(data)
        counts = {level: sum(level in c.baselines for c in data.controls) for level in ("low", "moderate", "high")}
        self.stdout.write(self.style.SUCCESS(
            f"{data.title} (v{data.version}): {result['families']} families, "
            f"{result['created']} controls created, {result['updated']} updated. "
            f"Baselines: low={counts['low']} moderate={counts['moderate']} high={counts['high']}"
        ))
