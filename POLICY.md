# Screening alert review: identity SOP

You review name screening alerts for a payments company. Screening compares each customer with sanctions, PEP, enforcement and adverse media lists and raises an alert when a name looks similar. Each alert has one or more **hits**: list profiles that might be the customer. For every hit, decide whether it is the customer.

## Decisions

| Decision | Meaning |
|---|---|
| `DIFFERENT_ENTITY` | The evidence shows the hit is a different person or company. The hit is cleared. |
| `SAME_ENTITY` | The evidence shows the hit is the customer. The alert goes to the compliance team. |
| `REVIEW` | The evidence cannot settle it. A person looks at it. |

An alert is cleared only when every hit in it is `DIFFERENT_ENTITY`. Clearing a hit that is the customer is the worst mistake; when in doubt, `REVIEW`.

## Principles

1. **Identity, not policy.** Decide whether the hit is the customer. How serious the listing is, or whether the customer would still be acceptable, does not matter here.

2. **Know who the customer is before comparing.** The alert shows the customer as screened. Their full picture is spread over the bank's systems, which do not share one key: the system of record, accounts, onboarding, the KYC provider and the support tool. Follow whatever link the alert carries. A link can lead to more than one person; the screened details then pick between them, as in a search without a link. Without a link, find the records that fit what was screened: a full, preferred or login name that agrees with the screened name (principle 8; screened names can carry nicknames and typos), a date of birth equal to the screened one in every part both give, the screened country as residence or nationality, and the screened city in the record's city or address. Never use another customer's records.

3. **One person, one picture.** Records that share a phone number and the same full date of birth belong to the same person, and so do records whose approved identity checks carry the same document number; a record linked to one of them in either way belongs to that person too. All their facts count. Sharing a phone or an address alone does not: family members often do. If more than one person fits an alert, decide the hit for each; if they all lead to the same decision, give it, otherwise the decision is `REVIEW` with `AMBIGUOUS_CUSTOMER_RECORD`. Either way `customer_record_id` is `AMBIGUOUS`. When one person has several records, any of them is accepted as `customer_record_id`.

4. **Verified beats declared.** The most recent *approved* identity check of the person is the most reliable source for their legal name, date of birth and document country, whether it is recorded by the KYC provider or only in a note by the onboarding team. Rejected or expired checks are not evidence. The verified legal name outranks the name on the customer record and the screened name, which can be nicknames, login names or typos.

5. **Gather the hit's facts wherever they are.** A hit's date of birth may be its `dobs` field, a sentence in the first paragraph of its profile notes (an age at a date gives two possible birth years: someone aged 45 in March 2019 was born in 1973 or 1974), or, when neither gives one, web search results for its name. Most search results are about other people with the same name: a result is about the hit only if it describes the same kind of listing in a country tied to the hit. The kind of listing follows the hit's primary category (or its first category): Sanctions: "a sanctioned individual"; PEP: "a politically exposed person"; Enforcement: "the subject of enforcement action"; Adverse Media: "named in adverse media"; SOE: "a state-owned enterprise official"; any other category: "named on a watchlist". The countries tied to a hit are its `countries`, `nationality`, `citizenship`, `addresses` (the last part of each) and `place_of_birth`; "International" and "Europe" are not countries. Dated reports are exactly the English lines in the profile notes of the form "According to …; September 10, 2025: …"; other wordings do not count. This form and the listing phrases above are worded the same in the unseen set. Dates inside hit profiles are written as the provider wrote them. For companies, only the `dobs` field is an incorporation date.

6. **Clear only on a contradiction.** A hit is a different entity only when a fact contradicts it:
   - **Time:** the customer was younger than 16 at the earliest dated report, or a company was incorporated after it; or the profile gives a date of death before the customer was screened.
   - **Date of birth:** every birth date the hit gives is contradicted: the customer's birth year is more than 1 year outside it, or both give a month in the same year and the months (or days) differ. One agreeing date is enough to prevent this.
   - **Location:** every country tied to the customer (residence and nationality on all their records, the approved identity document, and places the notes say they lived) differs from every country tied to the hit. Codes and nationalities are countries; territories count as their own country. A country difference does not clear a hit whose name and date of birth agree: that hit is `REVIEW`.
   - **Name:** the customer's verified legal name agrees with none of the hit's names or aliases (principle 8), even if the name on their record does.
   - **Type:** one is a person and the other a company.

7. **Confirm only on agreement.** Dates of birth agree when the customer's birth year is one of the hit's possible birth years and every part both give (month, day) is equal; a birth year alone can agree with a full date. Confirm a person when name and date of birth agree and nothing contradicts them; a company when name and country agree and nothing contradicts them. Otherwise, `REVIEW`.

8. **Names.** Compare name parts ignoring case, accents, punctuation and anything in brackets; single letters are initials, not parts, and each distinct part counts once. Two parts match when they are identical, are listed together in `name_variants.json`, are written together or apart (Abdulsalam matches Abdul Salam, counting as one part that covers both), or differ by at most 1 edit for parts of 4 to 6 letters and 2 for longer ones (an edit adds, removes or changes one letter, so swapping two letters is two edits; parts shorter than 4 letters must be identical; the shorter part's length decides). Names agree when at least two parts match, or every part of the shorter name matches. Aliases count as names, nicknames included. Placeholders (NA, N/A, TEST, UNKNOWN, XXX, NONE, digits and the like) are not name parts: an individual customer whose names have fewer than two real parts can be neither confirmed nor cleared on name; a hit's single-part alias can still agree with a customer's name. For companies, the legal forms listed in `name_variants.json` (Ltd, AB, GmbH, SA and the rest) are not name parts.

9. **Cite what you used.** Every decision names the records it relied on by their IDs, and the customer record it resolved (`null` if none was found). Cite what decided the hit, not everything you looked at.

## Reason codes

Give the main reason with one code that belongs to the decision. When several apply, any of them is accepted.

| Decision | Reason code | Use it when |
|---|---|---|
| `DIFFERENT_ENTITY` | `TEMPORAL_IMPOSSIBILITY` | The customer could not have done what the hit's profile reports: too young, or not yet incorporated, at the earliest dated report |
| `DIFFERENT_ENTITY` | `DOB_MISMATCH` | The customer's date of birth (or a company's incorporation date) contradicts every birth date the hit gives |
| `DIFFERENT_ENTITY` | `LOCATION_MISMATCH` | Every country tied to the customer differs from every country tied to the hit |
| `DIFFERENT_ENTITY` | `NAME_MISMATCH_VERIFIED` | The customer's verified legal name does not agree with any of the hit's names |
| `DIFFERENT_ENTITY` | `ENTITY_TYPE_MISMATCH` | One is a person and the other a company |
| `DIFFERENT_ENTITY` | `DECEASED` | The hit's profile gives a date of death before the customer was screened |
| `SAME_ENTITY` | `NAME_DOB_LOCATION_MATCH` | Name, date of birth and country all agree and nothing contradicts them |
| `SAME_ENTITY` | `NAME_DOB_MATCH` | Name and date of birth agree and nothing contradicts them |
| `SAME_ENTITY` | `NAME_LOCATION_MATCH` | Companies only: name and country agree and nothing contradicts them |
| `REVIEW` | `INSUFFICIENT_DATA` | Nothing settles it: no contradiction, and not enough agreement to confirm |
| `REVIEW` | `AMBIGUOUS_CUSTOMER_RECORD` | More than one person in the system of record fits the alert and they lead to different decisions |
