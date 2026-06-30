Master Roles File: 

- Contains master name list from Infinite Campus. All possible names authorized to create a chart in Infinite Campus. Names are formatted Last Name, First Name. Stripped of erroneous spaces. Ensured the first letters of Last Name and First Name are capital.  
- Contains work email associated with staffers name.  
- Contains position type associated with staffers name. Possible positions are APRN, RN, HT, SHA, Admin.

Holiday Calendar File:

- Contains a list of holiday dates where staff are not working, so no charts should be present on those dates.

Raw Data File:

- Represents the standardized csv file pulled from Infinite Campus.  
- Fields include Visit ID, Visit Date, Staff Name, Referred by (free text field entered by staffer to explain how the student was routed to the health office), Completed (Marked as 1 if staffer marked chart as complete, or 0 if in progress), Complaint Type (selected from dropdown of case types), Discharge (selected from dropdown of dispositions), Start Time (entered manually by staffer, time student entered health room), end time (entered manually by staffer, time student was released from health room), school name (autofilled, school health room), state ID (student’s unique identifier in statewide public school network, autofilled by infinite campus), clinical note (raw text data). 

Name Integrity Check:

- Looks at staff name column in Raw Data file and ensures every staff name in Raw Data file is found in Master Roles file. Flags if name is not found in Master Roles. Flag requires a new entry to be entered in Master Roles.  
- Calculates records per staff name, adds all up, and ensures that sum equals the number of rows in Raw Data file 

Audit Script: (one-hot encoding)

- Takes Raw data file, adds in an email column and role column so that the staffer’s email and role is in the file.  
- Check if Visit ID has duplicates/multiple instances. Since Visit ID is a unique identifier for a record, each visit id should have no other instance in the Raw Data file.  
- Check for Data Entry Duplicate: Flags if there is a record with the same staff name, same visit date, same start time, same school name, same state ID. Logical check for double chart of a visit.  
- Check if Completed field is 0\. Records should be marked complete, so all records Completed field should be 1\.  
- Checks if discharge field is null. All records need a discharge listed.   
- Checks if complaint field is null. All records need a complaint.  
- Checks if visit date is on a weekend (all records should be on weekday).  
- Check if visit date is on a holiday (references holiday list)  
- Checks if discharge time is missing  
- Checks if start time is missing.  
- Checks if start time is after discharge time.  
- Check if start time is equal to discharge time (vsit durations must be at least 1 minute)  
- Checks if Referred by field is blank.  
- Checks if visit duration is over 6 hours (upper bound of realistic visit duration)  
- Checks if start time is before 6:30 am (earliest time a staffer is present in a health room)  
- Checks if discharge time is after 5pm (latest time a staffer is present in a health room)  
- Check is SHA/HT/ADMIN are using discharge types/complaint types that are reserved for APRN/RN only.   
- Checks if clinical note is null (all charts must have explanations, so character count can never be 0\. 

Master Error File:

- Output of every visit flagged with at least one flag.  
- One visit may have multiple flags.  
- Replica of Raw Data File but with additional column (action required) and clinical note column dropped.   
- Action required column looks at boolean encoded error flag columns and outputs a standardized concise text message if true (e.g., Possible Duplicate Office Visit, Discharge Time is Missing, Referral is Missing, Start Time After Discharge Time, SHA/HT/ADMIN cannot use Referred to Psychiatric Care as Discharge, Visit Date is on Holiday, etc.)

Email Table Format:

- To search a record in Inifninte Campus, a user must input school name, student id, start time in that order.  
- Tables must be formatted with columns: staff name, school name, student id, start time, action required. Each row in the table represents a visit record.   
- Email includes brief introduction of email contents and link to google doc documentation guide (placeholder for now), which includes explanations of how to fix each action required standardized message.

Pipeline:

- Ingest csv from Infinite Campus (SQL: queries records from Health Office Visit module by searching for unique visit ID’s from all schools in current school year, output is csv).   
- Put csv through name integrity check and audit script to produce master file.  
- Data is ingested on Monday evening. Data pulled is the last week’s Monday-Friday.   
- Emails are sent out to all staff with errors (sourced from Master Error) at 7:00 am on Tuesday.   
- Email automation is orchestrated using Google Apps Script. Master file is sent to target google sheet via google sheets API, overwrites target sheet, tuesday 7 am the google apps script parses the sheet and sends emails. 

Other Notes:

- Vectorized operations in pandas?   
- Data subfolder (master roles, holiday calendar, raw data)  
- audit subfolder  
- apps script subfolder  
- read me  
- requirements  
- run book for new onboarding employees taking over the workflow/repo, security statement.   
- To ensure pipeline stability and prevent regression, the repository includes a local testing harness. The harness executes the audit engine against a synthetic dataset containing known compliance anomalies, verifying that the multi-label boolean flags trip deterministically before code deployment.   
- \#\#\# 📊 Synthetic Test Environment & Relational Integrity  
-   
- To evaluate the pipeline without exposing sensitive administrative data, the \`tests/\` directory contains fully synthetic data sets that preserve real-world relational integrity:  
-   
- 1\. \*\*\`mock\_master\_roles.csv\`:\*\* Establishes a baseline of authorized fictional personnel, matching fake names to mock organization email addresses and specific clinical roles.  
- 2\. \*\*\`mock\_raw\_data.csv\`:\*\* A synthetically generated encounter log designed to stress-test the validation engine. It includes deterministic data anomalies—such as intentional name formatting typos, mismatched role-based permissions, and chronological sequence errors—to verify that the testing harness catches 100% of the targeted compliance exceptions.  
-   
- To connect python with google, service account is made through the google cloud console. Google gives secure credential.json file stored alongside python script, in python that file is passed tt he integration library. On google sheet, click share, pass in the robot email address and give it editor permissions. Python script runs on a background task timer Monday evening, uses the JSON key to authenticate instantly, overwrite data.   
- .gitignore needs to be organized logically.   
- \#\#\# 🔒 Security & Data Minimization Architecture  
-   
- Because this utility processes student health logs containing Protected Health Information (PHI), the system enforces strict data isolation and minimization boundaries:  
-   
- \* \*\*Zero-Egress Text Processing:\*\* Clinical text notes (\`clinical\_note\`) are never transmitted, parsed by external NLP utilities, or exposed to third-party APIs. Narrative text de-identification introduces significant compliance risks; therefore, the script intentionally evaluates the narrative layer using a strict, stateless local validation rule (checking exclusively for null values/minimum character counts to ensure documentation exists).  
- \* \*\*Local Processing Boundaries:\*\* All validation logic—including data structure audits, duplicate detection, and rule matching—executes entirely within the secure local environment\[cite: 2\]. No patient data ever leaves the infrastructure boundary during the audit phase\[cite: 2\].  
- \* \*\*Stateless Cloud Handoff:\*\* The downstream data pushed to the Google Sheets messaging layer is completely stripped of the raw narrative text, minimizing the data footprint to the absolute bare minimum required for staff notification (School Name, Student ID, Start Time, and the standardized error tag)\[cite: 2\].

  ## **The Ideal Mock Data Scale**

Keep it compact, clean, and highly controlled:

* **`mock_raw_data.csv`:** **20 to 50 rows total.**  
  * This is small enough that a reviewer can skim the raw text file directly on GitHub, yet large enough to hold a diverse mix of clean rows and flagged anomalies.  
* Fictional Staff Names: **4 to 5 unique names.**  
  * Include 3 or 4 names that are properly matched in your roles file, plus 1 unmapped name to intentionally trip your `Name Integrity Check`.  
* **Fictional Schools:** **3 to 4 unique schools.**  
  * For example: `"Kahmehamha Elementary"`, `"Aloha Middle School"`, and `"Pacific High School"`. This is plenty to show how your script parses regional formatting without creating a massive matrix.  
* **`mock_master_roles.csv`:** **5 to 10 rows total.**  
  * Just enough to establish a clean relational baseline for your fake staff and their explicit clinical tiers (APRN, RN, SHA, etc.).

  ## **🎯 How to Distribute Your Test Cases**

With roughly 30 total rows in `mock_raw_data.csv`, you should aim for a **50/50 split** between passing and failing data to cleanly show off your terminal output:

1. **15 Clean Rows:** Standard data where timestamps match, names are spelled perfectly, fields are populated, and role permissions are respected. These rows should slide through the pipeline cleanly.  
2. **15 Flagged Rows:** Intentionally break exactly one rule per row so your test results prove your script can handle everything.  
   * *Row 20:* Set the start time to 7:00 AM and discharge to 6:55 AM (Trips sequence error).  
   * *Row 21:* Leave the clinical note blank (Trips null check).  
   * *Row 22:* Use a date that matches your `mock_holiday_calendar.csv` (Trips holiday exception).  
- 