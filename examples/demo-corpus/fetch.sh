#!/usr/bin/env bash
# Fetch the demo corpus into ./documents and verify it against manifest.json.
#
# The sources are public and redistributable (see sources.md). The binaries are
# not committed; this script reproduces the exact bytes the manifest attests.
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p documents

get() {
  local name="$1" url="$2"
  if [ -s "documents/$name" ]; then
    echo "have  $name"
    return
  fi
  echo "fetch $name"
  curl -fSL --retry 3 --retry-delay 2 --max-time 300 -A "Mozilla/5.0 (compatible; OntoSkills corpus fetch)" \
    -o "documents/$name" "$url"
}

get msc-core-terms.docx \
  "https://assets.publishing.service.gov.uk/media/68af256b969253904d1558e5/MSC_-_Core_Terms_-_E_W_-_Word_v2.2A_2025.DOCX"
get midtier-core-terms.docx \
  "https://assets.publishing.service.gov.uk/media/68aeee2b960e2d135b4c8e85/Mid-Tier_Core_Terms_Word_v1.3A_2025.docx"
get midtier-schedule20.docx \
  "https://assets.publishing.service.gov.uk/media/67b490bf4e79a175a4c2fe45/Mid-Tier_Schedule_20__Processing_Data__Word_v1.3_2025.DOCX"
get eu-scc-2021-914.pdf \
  "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32021D0914"
get eu-gdpr-2016-679.pdf \
  "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32016R0679"
get eu-ai-act-2024-1689.pdf \
  "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32024R1689"
get uk-ai-playbook.pdf \
  "https://assets.publishing.service.gov.uk/media/67aca2f7e400ae62338324bd/AI_Playbook_for_the_UK_Government__12_02_.pdf"
get nist-csf-2.0.pdf \
  "https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.29.pdf"
get nist-ai-rmf-1.0.pdf \
  "https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf"
get tna-contractual-records.pdf \
  "https://cdn.nationalarchives.gov.uk/documents/information-management/sched_contractual.pdf"
get tna-accounting-records.pdf \
  "https://cdn.nationalarchives.gov.uk/documents/information-management/sched_accounting.pdf"
get eu-tender-annex-a5.pdf \
  "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/tender-details/docs/5a2ed580-8348-4114-8e72-ca458ac08eb0-CN/EC-HOME-2025-OP-0009_Annex%20A5_Draft%20FWC%20services_V1.pdf"
get uk-cyber-security-standard.html \
  "https://www.security.gov.uk/policy-and-guidance/the-cyber-security-standard/"
get ncsc-cloud-security-principles-summary.pdf \
  "https://assets.publishing.service.gov.uk/media/5a7d7abfed915d269ba8aea2/Summary_of_Cloud_Security_Principles.pdf"

if [ -f manifest.json ]; then
  python3 build_manifest.py --verify
else
  python3 build_manifest.py
fi
