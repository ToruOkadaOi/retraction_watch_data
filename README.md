# Retraction Watch Data

This repository contains the latest dataset from Retraction Watch, generated on 2026-10-23.

A mirror of [Crossref's Retraction Watch dataset](https://gitlab.com/crossref/retraction-watch-data), with a knowledge graph and a public read-only API backed by Neo4j Aura.

## Hosted services

### Research dashboard

[Open the research dashboard](https://toruokadaoi.github.io/retraction_watch_data/) to browse notice statistics, filter records, and explore connected journals and shared names. Select a record to inspect its complete source fields.

Graph exploration loads one neighborhood at a time and shows at most 150 nodes and 300 connections. You can export the visible neighborhood as JSON. The dashboard displays the hosted snapshot fingerprint; its charts count notices, rather than journal retraction rates.

The dashboard is also served [directly by the API](https://retraction-watch-data.onrender.com/dashboard/).

### Knowledge graph API

- Interactive documentation: [API docs](https://retraction-watch-data.onrender.com/docs)
- Base URL: [retraction-watch-data.onrender.com](https://retraction-watch-data.onrender.com)
- Readiness check: [Service readiness](https://retraction-watch-data.onrender.com/ready)
- Statistics: [Graph statistics](https://retraction-watch-data.onrender.com/api/statistics)

The free Render service may sleep while idle, so the first request can take about a minute.
Hosted graph refreshes run separately from CSV updates; the hosted snapshot may differ from this repository's CSV.

## What it does

- Search article records and graph nodes.
- Retrieve article details with complete author, institution, and reason lists.
- Find records by an exact author, institution, or reason name, including names without separate graph nodes.
- Inspect shared author-name and institution-name connections.
- View graph statistics and journal/reason rankings for retraction notices.

The hosted compact graph retains every article record in its imported snapshot.
Author and institution nodes represent exact name strings shared across records;
author-name matches are not verified person identities. Complete source lists remain
available on each article, including names that have no separate graph node.

## Try the API

Search article records:

```bash
curl --get 'https://retraction-watch-data.onrender.com/api/search' \
  --data-urlencode 'q=cancer' \
  --data-urlencode 'node_type=Article' \
  --data-urlencode 'limit=5'
```

Retrieve a record with its listed names and connected entities:

```bash
curl 'https://retraction-watch-data.onrender.com/api/articles/1'
```

See the [interactive documentation](https://retraction-watch-data.onrender.com/docs) for all endpoints and parameters.

<details>
<summary><strong>Getting started locally</strong></summary>

Requires Python 3.11 or later. From the repository directory:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Generate the full graph and its JSON, GraphML, RDF, and sample PNG exports:

```bash
python knowledge_graph.py
```

Or generate the compact Aura profile with a separate JSON snapshot and quota report:

```bash
python knowledge_graph.py --profile aura
```

Full outputs are written to `outputs/`; compact outputs go to `outputs/aura/`.
GitHub Actions also generates both profiles after dataset updates and uploads the
outputs as workflow artifacts instead of committing the large files to Git.

To serve a compact snapshot locally:

```bash
GRAPH_JSON_PATH=outputs/aura/knowledge_graph.json uvicorn api:app --host 127.0.0.1 --port 8000
```

Open [http://localhost:8000/docs](http://localhost:8000/docs) or [the dashboard](http://localhost:8000/dashboard/).

For a disposable preview built from the first 200 real CSV records, without connecting to Aura:

```bash
python scripts/preview_dashboard.py
```

Open http://localhost:8765/dashboard/. This preview leaves existing graph outputs unchanged.

</details>

See [KNOWLEDGE_GRAPH.md](KNOWLEDGE_GRAPH.md) for the graph schema, exports, Neo4j/Aura
imports, hosted deployment, and API reference; [QUICKSTART.md](QUICKSTART.md) for
setup; and [SECURITY.md](SECURITY.md) for deployment boundaries.

## About the Dataset

Research can be modified after publication, including being corrected or retracted. This is a natural part of the research process and important for accurately reporting changes. While members can deliver this information to us, Retraction Watch has also collected a large number of retractions. Many of these have not been reported by our members.

In September 2023, Crossref acquired the Retraction Watch database from the Center of Scientific Integrity and have made it publicly available. The database contains retractions gathered from publisher websites and is updated every working day by Retraction Watch. Some other update types, such as expressions of concern and corrections, are also included in the data, but these are not as comprehensive as retractions. Various methods are used to find retractions, including searching scholarly databases, checking publisher websites, web searches, and reports from the community. For further details, see [this document](https://retractionwatch.com/wp-content/uploads/2023/12/Building-The-Database.pdf).

Data in the csv file is comma-separated, with lists in a single entry separated by a semicolon (such as author names or reasons for retraction).

<details>
<summary><strong>CSV field definitions</strong></summary>

The column headings in the csv file are:

- _Record ID_: An internal identifier from Retraction Watch.
- _Title_: The title of the retracted or updated content.
- _Subject_: The subject area of the publication.
- _Institution_: Author affiliations, as given in the content.
- _Journal_: The source (serial, book, etc.) in which the research was published.
- _Publisher_: The organisation responsible for publication.
- _Country_: Countries included in author affiliations.
- _Author_: A list of author names.
- _URLS_: Links to relevant pages on the Retraction Watch website, including blog posts about the retraction.
- _ArticleType_: The content type, using a [list of types](https://retractionwatch.com/retraction-watch-database-user-guide/retraction-watch-database-user-guide-appendix-c-article-types/) maintained by Retraction Watch. Note that this isn’t the same as the Crossref work type.
- _RetractionDate_: The date of the published retraction.
- _RetractionDOI_: The DOI of the published retraction, if available. If there is no DOI, the value is either blank, 'unavailable', or 'Unavailable'.
- _RetractionPubMedID_: PubMED ID of the published retraction, if available. If there is no Pubmed ID, the value is either blank or 0.
- _OriginalPaperDate_: The publication date of the retracted content.
- _OriginalPaperDOI_: The DOI of the retracted publication, if available. If there is no DOI, the value is either blank, 'unavailable', or 'Unavailable'.
- _OriginalPaperPubMedID_: PubMED ID of the original publication, if available. If there is no Pubmed ID, the value is either blank or 0.
- _RetractionNature_: The type of update notice, which can be Retraction, Correction, Expression of concern, or Reinstatement. Note that these are different to the [list of update types](/crossmark/participating-in-crossmark/#00279) in the Crossref schema.
- _Reason_: A list of reasons for retraction. This uses a [controlled vocabulary](https://retractionwatch.com/retraction-watch-database-user-guide/retraction-watch-database-user-guide-appendix-b-reasons/) maintained by Retraction Watch.
- _Paywalled_: Is a fee or paid subscription required to access the retraction notice? Note that there can be cases where this changes some time after publication of the notice.
- _Notes_: Additional comments about the retraction.

These fields are also documented [on the Retraction Watch website](https://retractionwatch.com/retraction-watch-database-user-guide/retraction-watch-database-user-guide-appendix-a-fields/).  Changes to the field names and vocabulary used [are recorded by Retraction Watch](https://retractionwatch.com/retraction-watch-database-user-guide/retraction-watch-database-user-guide-appendix-d-changes/).

</details>
