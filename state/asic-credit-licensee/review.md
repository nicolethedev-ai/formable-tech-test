# Review: asic-credit-licensee

Dataset: ASIC – Credit Licensee Dataset
Publisher: Australian Securities and Investments Commission (ASIC)
Licence: cc-by
Format: csv | rows: 4307 | agent says this is: Australian credit licensees regulated by ASIC
URL: https://data.gov.au/data/dataset/fa0b0d71-b8b8-4af8-bc59-0b000ce0d5e4/resource/35953a01-a9a8-4609-8566-c9fa7de465d3/download/credit_lic_202610.csv

## Validation on 500 unseen rows: PASS after 1 revision(s)

## Mapping

| source field | canonical field | transforms | confidence | emitted | rejected | rationale |
| --- | --- | --- | --- | --- | --- | --- |
| CRED_LIC_NAME | entity.legal_name | trim | 0.95 | 500 | 0 | Column explicitly contains licensee names; 100% non-null, 150 distinct values. |
| CRED_LIC_BN | entity.trading_name | trim | 0.85 | 184 | 0 | BN likely stands for Business Name; 35.3% non-null with 53 distinct trading names. |
| CRED_LIC_ABN_ACN | entity.abn | digits_only | 0.87 | 456 | 44 | 87.3% of values pass ABN checksum validation; column name indicates ABN/ACN mix. |
| CRED_LIC_STATUS | entity.status | map | 0.90 | 500 | 0 | All 150 rows show 'APPR' (approved); maps to active status. |
| CRED_LIC_START_DT | entity.date_registered | date_parse | 0.95 | 500 | 0 | Column contains license start dates in DD/MM/YYYY format; 100% non-null. |
| CRED_LIC_LOCALITY | address.locality | trim | 0.95 | 500 | 0 | Column explicitly contains locality names; 100% non-null, 108 distinct values. |
| CRED_LIC_STATE | address.state | upper | 0.98 | 500 | 0 | Column contains 2-letter state codes; 100% non-null with state_like=1.0. |
| CRED_LIC_PCODE | address.postcode | trim | 0.95 | 500 | 0 | Column contains 4-digit Australian postcodes; 100% non-null. |

## Not mapped (left empty on purpose)

- CRED_LIC_ACN: Only 8.7% pass ACN checksum; most values are ABN. Mapping rejected due to 94% pattern mismatch on validation.
- CRED_LIC_LAT: Latitude coordinate; no canonical field for geographic coordinates in ontology.
- CRED_LIC_LNG: Longitude coordinate; no canonical field for geographic coordinates in ontology.
- CRED_LIC_AFSL_NUM: AFSL (Australian Financial Services Licence) number; distinct from credit licence, no canonical field.
- CRED_LIC_AUTHORISATIONS: Long-form license authorisation text; no canonical field for regulatory authorisation details.
- CRED_LIC_EDRS: External Dispute Resolution Scheme codes (AFCA, FOS, COSL); no canonical field for dispute resolution scheme.
- REGISTER_NAME: Metadata field ('Credit Licence'); not entity data.

## Issues

- [warning] sparse_field entity.trading_name: only 37% of rows have a value

## 5 sample records: raw -> canonical

- h-0696794fbdbcc287 | entity.legal_name: 'PLANNING PARTNERS PTY. LTD.' -> 'PLANNING PARTNERS PTY. LTD.'
- h-0696794fbdbcc287 | entity.trading_name: 'PLANNING PARTNERS' -> 'PLANNING PARTNERS'
- h-0696794fbdbcc287 | entity.abn: '64090069239' -> '64090069239'
- h-0696794fbdbcc287 | entity.status: 'APPR' -> 'active'
- h-0696794fbdbcc287 | entity.date_registered: '28/02/2011' -> '2011-02-28'
- h-0696794fbdbcc287 | address.locality: 'CAMBERWELL' -> 'CAMBERWELL'
- h-0696794fbdbcc287 | address.state: 'VIC' -> 'VIC'
- h-0696794fbdbcc287 | address.postcode: '3124' -> '3124'
- h-169a3713c79a1b6a | entity.legal_name: 'FYG PLANNERS PTY LTD' -> 'FYG PLANNERS PTY LTD'
- h-169a3713c79a1b6a | entity.abn: '55094972540' -> '55094972540'
- h-169a3713c79a1b6a | entity.status: 'APPR' -> 'active'
- h-169a3713c79a1b6a | entity.date_registered: '21/02/2011' -> '2011-02-21'
- h-169a3713c79a1b6a | address.locality: 'CAIRNS' -> 'CAIRNS'
- h-169a3713c79a1b6a | address.state: 'QLD' -> 'QLD'
- h-169a3713c79a1b6a | address.postcode: '4870' -> '4870'
- h-ad98ddceff67be1c | entity.legal_name: 'FIRST MORTGAGE MANAGED INVESTMENTS LIMITED' -> 'FIRST MORTGAGE MANAGED INVESTMENTS LIMITED'
- h-ad98ddceff67be1c | entity.abn: '39089507899' -> '39089507899'
- h-ad98ddceff67be1c | entity.status: 'APPR' -> 'active'
- h-ad98ddceff67be1c | entity.date_registered: '07/03/2011' -> '2011-03-07'
- h-ad98ddceff67be1c | address.locality: 'BURLEIGH HEADS' -> 'BURLEIGH HEADS'
- h-ad98ddceff67be1c | address.state: 'QLD' -> 'QLD'
- h-ad98ddceff67be1c | address.postcode: '4220' -> '4220'
- h-39f0dfc231b7f5d8 | entity.legal_name: 'BUTLER & BUTLER INVESTMENT SERVICES PTY. LTD.' -> 'BUTLER & BUTLER INVESTMENT SERVICES PTY. LTD.'
- h-39f0dfc231b7f5d8 | entity.abn: '92053326944' -> '92053326944'
- h-39f0dfc231b7f5d8 | entity.status: 'APPR' -> 'active'
- h-39f0dfc231b7f5d8 | entity.date_registered: '11/02/2011' -> '2011-02-11'
- h-39f0dfc231b7f5d8 | address.locality: 'VICTOR HARBOR' -> 'VICTOR HARBOR'
- h-39f0dfc231b7f5d8 | address.state: 'SA' -> 'SA'
- h-39f0dfc231b7f5d8 | address.postcode: '5211' -> '5211'
- h-3e3cbade3b5c95d3 | entity.legal_name: 'ING BANK (AUSTRALIA) LIMITED' -> 'ING BANK (AUSTRALIA) LIMITED'