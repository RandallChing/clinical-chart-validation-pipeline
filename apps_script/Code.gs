/**
 * Hawaii DOE Chart Correction — Email Notification System
 * =========================================================
 * Reads the MasterErrorFile Google Sheet tab, groups flagged chart records
 * by staff email address, and sends each staff member a personalized HTML
 * table notification listing only the records they need to correct.
 *
 * Deployment Steps
 * ----------------
 * 1. Open the Google Sheet that Python pushes data to.
 * 2. Extensions → Apps Script → paste this file as Code.gs.
 * 3. Update SHEET_ID and TAB_NAME below to match your sheet.
 * 4. Triggers → Add Trigger → sendCorrectionEmails → Time-driven →
 *    Week timer → Every Tuesday → 7:00–8:00 AM.
 * 5. Authorize the script when prompted (requires Gmail send permission).
 *
 * Email Format
 * ------------
 * Each staff member receives one email per weekly audit cycle.
 * The email contains an HTML table with columns:
 *   School Name | State ID | Visit Date | Start Time | Action Required
 *
 * To locate a record in Infinite Campus: School Name → State ID → Start Time.
 */

// ─── CONFIGURATION — update before deploying ────────────────────────────────
const SHEET_ID    = "YOUR_GOOGLE_SHEET_ID_HERE"; // Google Sheet ID from the URL
const TAB_NAME    = "MasterErrorFile";            // Worksheet tab name
const SENDER_NAME = "Health Room Operations";     // Display name in From field
const GUIDE_URL   = "https://docs.google.com/document/d/PLACEHOLDER_DOC_ID";
// ────────────────────────────────────────────────────────────────────────────


/**
 * Main entry point — triggered every Tuesday at 7:00 AM.
 * Groups error records by staff email and dispatches one email per staffer.
 */
function sendCorrectionEmails() {
  const sheet = SpreadsheetApp.openById(SHEET_ID).getSheetByName(TAB_NAME);
  const data  = sheet.getDataRange().getValues();

  if (data.length <= 1) {
    Logger.log("No error records found in sheet. No emails sent.");
    return;
  }

  // Build column index map from header row
  const headers  = data[0];
  const colIndex = {};
  headers.forEach((h, i) => { colIndex[h] = i; });

  // Group data rows by staff email
  const emailMap = {};
  for (let i = 1; i < data.length; i++) {
    const row   = data[i];
    const email = row[colIndex["Email"]];
    if (!email || email === "UNKNOWN") continue;
    if (!emailMap[email]) emailMap[email] = [];
    emailMap[email].push(row);
  }

  const weekOf = getLastMondayString_();

  // Send one email per staff member
  for (const [email, rows] of Object.entries(emailMap)) {
    const staffName = rows[0][colIndex["Staff Name"]];
    const tableRows = rows.map(row => buildTableRow_(row, colIndex)).join("");

    const htmlBody = buildEmailHtml_(staffName, tableRows, weekOf);

    MailApp.sendEmail({
      to:       email,
      subject:  `[Action Required] Chart Correction Notice — Week of ${weekOf}`,
      htmlBody: htmlBody,
      name:     SENDER_NAME,
    });

    Logger.log(`Sent to ${email}: ${rows.length} flagged record(s).`);
  }

  Logger.log("All correction emails dispatched successfully.");
}


// ─── Private Helpers ─────────────────────────────────────────────────────────

/**
 * Builds one <tr> for the notification table.
 * Only minimal identifiers are included — no clinical note text, no PHI
 * beyond what staff need to locate the record in Infinite Campus.
 */
function buildTableRow_(row, colIndex) {
  const td = (val, color) =>
    `<td style="padding:8px 12px; border:1px solid #e0e0e0; ${color ? "color:" + color + ";" : ""}">${val || "—"}</td>`;

  return `
    <tr>
      ${td(row[colIndex["School Name"]])}
      ${td(row[colIndex["State ID"]])}
      ${td(row[colIndex["Visit Date"]])}
      ${td(row[colIndex["Start Time"]])}
      ${td(row[colIndex["Action Required"]], "#c0392b")}
    </tr>`;
}


/**
 * Builds the full HTML email body for one staff member.
 */
function buildEmailHtml_(staffName, tableRows, weekOf) {
  return `
<!DOCTYPE html>
<html lang="en">
<body style="margin:0; padding:0; font-family:Arial, Helvetica, sans-serif; background:#f4f4f4;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4; padding:24px 0;">
    <tr>
      <td align="center">
        <table width="640" cellpadding="0" cellspacing="0"
               style="background:#ffffff; border-radius:6px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.08);">

          <!-- Header -->
          <tr>
            <td style="background:#2c3e50; padding:20px 28px;">
              <p style="margin:0; color:#ffffff; font-size:18px; font-weight:bold;">
                Chart Correction Notice
              </p>
              <p style="margin:4px 0 0; color:#95a5a6; font-size:13px;">
                Weekly Data Integrity Audit — Week of ${weekOf}
              </p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:24px 28px;">
              <p style="margin:0 0 12px; color:#333; font-size:14px;">
                Hi ${staffName},
              </p>
              <p style="margin:0 0 20px; color:#555; font-size:14px; line-height:1.6;">
                The weekly data integrity audit has flagged the following chart records
                requiring your attention. To locate each record in Infinite Campus,
                search by <strong>School Name → State ID → Start Time</strong>.
              </p>
              <p style="margin:0 0 16px; color:#555; font-size:14px;">
                See the
                <a href="${GUIDE_URL}" style="color:#2980b9;">Chart Correction Guide</a>
                for step-by-step instructions on resolving each error type.
              </p>

              <!-- Error Table -->
              <table width="100%" cellpadding="0" cellspacing="0"
                     style="border-collapse:collapse; font-size:13px;">
                <thead>
                  <tr style="background:#2c3e50; color:#ffffff;">
                    <th style="padding:10px 12px; text-align:left; border:1px solid #34495e;">School Name</th>
                    <th style="padding:10px 12px; text-align:left; border:1px solid #34495e;">State ID</th>
                    <th style="padding:10px 12px; text-align:left; border:1px solid #34495e;">Visit Date</th>
                    <th style="padding:10px 12px; text-align:left; border:1px solid #34495e;">Start Time</th>
                    <th style="padding:10px 12px; text-align:left; border:1px solid #34495e;">Action Required</th>
                  </tr>
                </thead>
                <tbody>
                  ${tableRows}
                </tbody>
              </table>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#f8f8f8; padding:16px 28px; border-top:1px solid #e0e0e0;">
              <p style="margin:0; color:#999; font-size:11px; line-height:1.5;">
                This is an automated notification. Do not reply to this email.<br>
                Contact your department lead or system administrator if you have
                questions about a specific flag.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>`;
}


/**
 * Returns the Monday of the previous calendar week as MM/DD/YYYY.
 * Used in the email subject line to identify which data window was audited.
 */
function getLastMondayString_() {
  const today      = new Date();
  const dayOfWeek  = today.getDay();                     // 0=Sun … 6=Sat
  const daysBack   = (dayOfWeek === 0 ? 6 : dayOfWeek - 1) + 7;
  const lastMonday = new Date(today);
  lastMonday.setDate(today.getDate() - daysBack);
  return Utilities.formatDate(
    lastMonday,
    Session.getScriptTimeZone(),
    "MM/dd/yyyy"
  );
}
