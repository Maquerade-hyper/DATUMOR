# Third-Party License Review

Review scope: DATUMOR Python dependencies and the current open-source release.

## Project license

DATUMOR source code: Apache License 2.0 (`Apache-2.0`).

This license applies to DATUMOR's own code. It does not replace or override
the licenses of third-party packages.

## Reviewed license exceptions

| Component | License | Decision |
|---|---|---|
| Psycopg 3 | LGPL-3.0 | Retain. Include applicable license and notices. Review redistribution of psycopg-binary and bundled client libraries. |
| Certifi | MPL-2.0 | Retain. Preserve notices; review obligations if MPL-covered files are modified. |
| tqdm | MPL-2.0 AND MIT | Retain. Preserve its mixed-license notice; do not describe the entire package as MIT-only. |
| Mako | MIT | Retain. Preserve copyright and license notice. |
| PyMuPDF | AGPL-3.0 or commercial | Removed from the PDF extraction implementation in favor of pdfplumber. Must remain absent from runtime dependencies unless separately approved. |

## Psycopg distribution review

DATUMOR uses the `psycopg[binary]` installation extra.

Before distributing a prebuilt Docker image or other binary package:

- Include the applicable LGPL-3.0 license text and third-party notices.
- Inspect the installed `psycopg` and `psycopg_binary` distribution license files.
- Inspect notices for bundled client libraries, including libpq and any other
  bundled components.
- Preserve upstream copyright and license notices.
- If modifying LGPL-covered components, document the modifications and
  satisfy the applicable source/relinking requirements.
- Do not impose terms on recipients that restrict rights granted by the LGPL.

The exact obligations depend on the distribution format and the components
actually included. Obtain legal review before commercial binary redistribution.

## MPL review

Certifi and portions of tqdm carry MPL-2.0 licensing.

- Preserve the upstream license and copyright notices.
- Do not remove MPL notices.
- If modifying MPL-covered source files and distributing the modified
  versions, make those covered files available under MPL-2.0 as required.
- Keep the package's actual mixed-license terms in the notices inventory.

## PyMuPDF exclusion

The PDF extraction implementation was changed to use pdfplumber and ReportLab.
The release audit must confirm:
- No PyMuPDF import remains in application or test source.
- PyMuPDF is absent from requirements.txt.
- PyMuPDF is absent from the deployment environment.

## Release decision

Status: CONDITIONAL PASS ? NOTICE AND DISTRIBUTION REVIEW REQUIRED.

No automatic incompatibility has been established from the known license
findings. This is not a legal opinion or a certification of every dependency.

Before release:
1. Review the generated THIRD_PARTY_NOTICES.md against runtime dependencies.
2. Verify Psycopg and bundled binary-library notices.
3. Verify the actual Docker image dependency inventory.
4. Confirm all third-party notices accompany distributed artifacts.
5. Obtain legal review for LGPL/MPL redistribution obligations where needed.

## Audit limitations

Package metadata and license labels are not a substitute for inspecting the
actual license files and bundled components. The installed environment may
contain development-only packages. The deployment image and source
requirements must be audited separately.

## Verified Docker Runtime License Addendum

Verified against the running DATUMOR API container on 2026-11-13.

| Package/component | Version | License |
|---|---:|---|
| psycopg | 3.2.6 | LGPL-3.0 |
| psycopg-binary | 3.2.6 | LGPL-3.0 |
| libpq bundled by Psycopg binary | 17.0.4 | PostgreSQL License |
| certifi | 2026.10.23 | MPL-2.0 |
| tqdm | 4.70.1 | MPL-2.0 AND MIT |
| Mako | 1.4.3 | MIT |
| pdfplumber | 0.11.10 | MIT |
| ReportLab | 4.5.1 | BSD |

Psycopg's binary installation packages its client libraries. The bundled
libpq component uses the PostgreSQL License. Preserve the relevant upstream
notices when redistributing the image.

Mako and pdfplumber expose license files in their installed distributions
even though their package metadata does not populate the License field.
Their upstream projects identify them as MIT-licensed.

ReportLab's open-source toolkit is BSD-licensed.

This addendum supplements the installed-environment inventory. It does not
replace the original license files or constitute legal advice.

## M10.3 Final Runtime License Review

Review date: 2026-11-13

### Runtime inventory findings

- Runtime and development package inventories generated separately.
- Docker runtime contains PyJWT 2.10.1 and Redis 6.2.0.
- PyMuPDF is absent from the rebuilt runtime.
- pytest, pytest-cov, and Ruff are absent from the rebuilt runtime.
- pdfplumber 0.11.10 and ReportLab 4.5.1 are present.
- Psycopg 3.2.6 and psycopg-binary 3.2.6 identify LGPLv3 licensing.
- Certifi identifies MPL-2.0 licensing.
- tqdm identifies MPL-2.0 AND MIT licensing.
- MinIO SDK was removed from runtime requirements after isolated and original Windows test suites both passed (697 passed, 1 skipped). The application uses boto3 for S3-compatible storage; legacy MINIO_* environment-variable aliases remain for compatibility.

### Release conditions

- Preserve applicable third-party license texts and notices.
- Review LGPLv3 obligations for Psycopg and its binary distribution.
- Review MPL obligations and bundled dependency notices.
- Verify licenses for transitive and bundled native dependencies.
- Obtain appropriate legal review before commercial redistribution.

This is a technical inventory, not legal certification.
Final redistribution approval remains pending.

## Expanded Psycopg Native-Component Review — 2026-11-14

The Linux Docker runtime inspection of `psycopg-binary==3.2.6` identified
14 bundled shared-library files covering PostgreSQL, OpenSSL, MIT Kerberos,
OpenLDAP, Cyrus SASL, PCRE, SELinux, e2fsprogs, and keyutils components.

The expanded preliminary attribution inventory is recorded in
`docs/THIRD_PARTY_NOTICES.md`.

Important limitations:

- The installed wheel's exact upstream source revisions for these bundled
  libraries have not been established.
- The embedded-string inspection did not produce usable licence evidence.
- Some upstream projects contain multiple copyright holders and
  component-specific licences.
- The upstream project licence alone does not prove the licence of every
  file in the bundled binary.
- Complete applicable copyright and licence notices have not yet been
  assembled and verified for all 14 files.

Release implications:

1. Keep human/legal review pending.
2. Do not claim complete native-component licence compliance yet.
3. Before redistributing Docker images or other binaries, verify wheel
   provenance, exact component versions, complete notices, and applicable
   LGPL, Apache, BSD, and other licence obligations.
4. Re-run this inventory whenever the Psycopg binary wheel or runtime
   image changes.

The source-code release review and binary/Docker-image redistribution
review must remain separate. This record is an engineering audit note,
not legal advice or legal clearance.
