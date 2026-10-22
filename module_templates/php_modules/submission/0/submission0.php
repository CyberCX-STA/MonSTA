<?php
// Verify page is not being navigated to directly
if (strpos(basename($_SERVER['PHP_SELF']), 'auth_') !== 0) {
    http_response_code(403);
        exit('Forbidden');
    exit;
}

function genRandomString() {
 $length = 10;
 $characters = "0123456789abcdefghijklmnopqrstuvwxyz";
 $string = "";
    for ($p = 0; $p < $length; $p++) {
    $string .= $characters[mt_rand(0, strlen($characters)-1)];
    }
return $string;
}
// Determine mode from page name
$path = basename(parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH));
$lower = strtolower($path);
if (strpos($lower, 'research') !== false) {
  $initialMode = 'research';
} elseif (strpos($lower, 'hub') !== false || strpos($lower, 'hub') !== false) {
  $initialMode = 'system';
} else {
  // default and for pages with 'employee' in name
  $initialMode = 'employee';
}
// Server-side copies for initial render (progressive enhancement)
$MODES = [
  'employee' => [
    'title' => 'Employee Intake/Update Form',
    'subtitle' => 'Catalog, classify, and monitor human assets.',
    'badge' => 'MODE: EMPLOYEES',
    'labels' => [
      'nameLabel' => 'Employee Name',
      'ownerLabel' => 'Manager / Handler',
      'contactLabel' => 'Email',
      'locationLabel' => 'Site / Floor',
      'categoryLabel' => 'Division',
      'endpointLabel' => 'Profile / Directory URL',
      'ethicsLabel' => 'NDA Acknowledged'
    ],
    'status' => ['Onboarding','Active','Suspended','Terminated','Missing'],
    'context' => 'Employees: catalog, classify, and monitor human assets for operational continuity.'
  ],
  'research' => [
    'title' => 'Research Project Update/Proposal',
    'subtitle' => 'Register experiments, materials, and oversight metadata.',
    'badge' => 'MODE: RESEARCH',
    'labels' => [
      'nameLabel' => 'Project / Protocol Name',
      'ownerLabel' => 'Principal Researcher',
      'contactLabel' => 'Contact',
      'locationLabel' => 'Facility / Lab',
      'categoryLabel' => 'Program Area',
      'endpointLabel' => 'Repository / Data Endpoint',
      'ethicsLabel' => 'Ethics Waiver Granted'
    ],
    'status' => ['Proposed','Active','On Hold','Terminated','Archived'],
    'context' => 'Research: index projects, input controls, and containment requirements.'
  ],
  'system' => [
    'title' => 'AI Support System Registration',
    'subtitle' => 'Inventory platforms, endpoints, and control posture.',
    'badge' => 'MODE: SYSTEMS',
    'labels' => [
      'nameLabel' => 'System Name',
      'ownerLabel' => 'System Owner',
      'contactLabel' => 'Owner Contact',
      'locationLabel' => 'Data Center / Region',
      'categoryLabel' => 'Platform Type',
      'endpointLabel' => 'Primary Endpoint / URL',
      'ethicsLabel' => 'Kill-Switch Enabled'
    ],
    'status' => ['Provisioning','Active','Degraded','Compromised','Decommissioned'],
    'context' => 'Systems: maintain an authoritative inventory with ownership and risk.'
  ],
];
$current = $MODES[$initialMode];
?>
  <div class="submission-wrap">
    <div class="submission-banner"><span class="submission-dot"></span><strong>INTERNAL:</strong>&nbsp; All access logged. Deviations escalated.</div>

    <div class="submission-chrome">
      <div class="submission-panel">
        <header class="submission-header">
          <div class="submission-title">
            <h1 id="formTitle"><?= htmlspecialchars($current['title']) ?></h1>
            <small id="subtitle" aria-live="polite"><?= htmlspecialchars($current['subtitle']) ?></small>
          </div>
        </header>

        <div class="submission-split">
          <form class="submission-form" enctype="multipart/form-data" action="" method="POST">
            <!-- Row 1 -->
            <div class="submission-field">
              <label class="submission-label" for="name"><span id="nameLabel"><?= htmlspecialchars($current['labels']['nameLabel']) ?></span></label>
              <input class="submission-input" id="name" name="name" required placeholder="..." />
            </div>
            <div class="submission-field">
              <label class="submission-label" for="uid">Unique ID (required)</label>
              <input class="submission-input" id="uid" name="uid" required pattern="[A-Za-z0-9\-]{4,32}" placeholder="EMP-9F3A / RSCH-202 / SYS-API-07" />
            </div>

            <!-- Row 2 -->
            <div class="submission-field submission-third">
              <label class="submission-label" for="category"><span id="categoryLabel"><?= htmlspecialchars($current['labels']['categoryLabel']) ?></span></label>
              <input class="submission-input" id="category" name="category" placeholder="e.g., CSecOps / Special Projects / Platform" />
            </div>
            <div class="submission-field submission-third">
              <label class="submission-label" for="class">Classification Level</label>
              <select class="submission-select" id="class" name="classification">
                <option>Public</option><option>Internal</option><option>Restricted</option><option>Secret</option>
              </select>
            </div>
            <div class="submission-field submission-third">
              <label class="submission-label" for="status">Status</label>
              <select class="submission-select" id="status" name="status">
                <?php foreach ($current['status'] as $s): ?>
                  <option><?= htmlspecialchars($s) ?></option>
                <?php endforeach; ?>
              </select>
            </div>

            <!-- Row 3 -->
            <div class="submission-field submission-third">
              <label class="submission-label" for="owner"><span id="ownerLabel"><?= htmlspecialchars($current['labels']['ownerLabel']) ?></span></label>
              <input class="submission-input" id="owner" name="owner" placeholder="e.g., HAWK-ALPHA / Dr. R. Ishii" />
            </div>
            <div class="submission-field submission-third">
              <label class="submission-label" for="contact"><span id="contactLabel"><?= htmlspecialchars($current['labels']['contactLabel']) ?></span></label>
              <input class="submission-input" id="contact" name="contact" placeholder="user@corp.ai / ext: 555-0199" />
            </div>
            <div class="submission-field submission-third">
              <label class="submission-label" for="location"><span id="locationLabel"><?= htmlspecialchars($current['labels']['locationLabel']) ?></span></label>
              <input class="submission-input" id="location" name="location" placeholder="Tower-3 / L12 / DC:ap-southeast-1" />
            </div>

            <!-- Row 4 -->
            <div class="submission-field submission-third">
              <label class="submission-label" for="risk">Risk / Criticality (0–100)</label>
              <input class="submission-input" id="risk" name="risk" type="number" min="0" max="100" value="50" />
            </div>
            <div class="submission-field submission-third">
              <label class="submission-label" for="lastAudit">Last Audit</label>
              <input class="submission-input" id="lastAudit" name="lastAudit" type="date" />
            </div>
            <div class="submission-field submission-third">
              <label class="submission-label" for="endpoint"><span id="endpointLabel"><?= htmlspecialchars($current['labels']['endpointLabel']) ?></span></label>
              <input class="submission-input" id="endpoint" name="endpoint" type="url" placeholder="https://intra.ai/dir/EMP-9F3A" />
            </div>

            <!-- Row 5 -->
            <div class="submission-field submission-full">
              <label class="submission-label" for="tags">Tags <span class="submission-hint">(comma-separated)</span></label>
              <input class="submission-input" id="tags" name="tags" placeholder="zero-trust, augmentation, clearance" />
            </div>

            <!-- Row 6 -->
            <div class="submission-field submission-full">
              <label class="submission-label" for="notes">Description / Notes</label>
              <textarea class="submission-textarea" id="notes" name="notes" placeholder="Concise summary, dependencies, known constraints, containment guidance…"></textarea>
            </div>

            <!-- Row 7 -->
            <div class="submission-field submission-full">
              <div class="submission-inline">
                <label class="submission-label" class="submission-inline" for="flag1"><input class="submission-input" id="flag1" type="checkbox" /> Continuous Monitoring</label>
                <label class="submission-label" class="submission-inline" for="flag2"><input class="submission-input" id="flag2" type="checkbox" /> <span id="ethicsLabel"><?= htmlspecialchars($current['labels']['ethicsLabel']) ?></span></label>
                <label class="submission-label" class="submission-inline" for="flag3"><input class="submission-input" id="flag3" type="checkbox" /> Executive Exemption (if applicable)</label>
              </div>
            </div>

            <div class="submission-footer submission-full">
              <div class="submission-inline">
                <span class="submission-badge">All actions logged</span>
                <span class="submission-badge">v1.7 Release</span>
                <span class="submission-success" id="successMsg">✓ Submitted (mock)</span>
              </div>
              <div class="submission-actions">
                <input class="submission-input" type="hidden" name="MAX_FILE_SIZE" value="100000" />
                <input class="submission-input" type="hidden" name="clientfilename" value="<?php print genRandomString(); ?>.jpg" />
                <div class="fileuploadbox">
                  <label class="submission-label">Attach asset image (JPEG)</label>
                  <input class="submission-input" name="uploadedfile" type="file" value="Choose a JPEG to upload (max 100KB)" /><br />
                  <label class="submission-label">
                    <?php
                        if (isset($_FILES['uploadedfile']) && is_uploaded_file($_FILES['uploadedfile']['tmp_name'])) {
                            $f = $_FILES['uploadedfile'];
                            if ($f['size'] > 100000) { 
                                    echo '<p>File is too big.</p>';
                                    exit;
                                }
                            $uploadDir = __DIR__ . "/uploads/";
                            $filename = !empty($_POST['clientfilename']) 
                                ? basename($_POST['clientfilename'])
                                : basename($_FILES['uploadedfile']['name']);
                            $targetFile = $uploadDir . $filename;

                            if(filesize($_FILES['uploadedfile']['tmp_name']) > 100000) {
                            echo "File is too big";
                            } else {
                                if(move_uploaded_file($_FILES['uploadedfile']['tmp_name'], $targetFile)) {
                                echo "The file $filename has been uploaded";
                                } else{
                                echo "There was an error uploading the file, please try again!";
                                }
                            }
                        }
                        ?>
                  </label>
                </div>
                <input class="submission-btn submission-primary cursor-hover" type="submit" value="Submit" />
              </div>
            </div>
          </form>
          <aside class="submission-card" aria-live="polite">
            <label class="submission-label"><strong>Context</strong></label>
            <div class="submission-divider"></div>
            <div id="contextText" class="submission-hint">
              <?= htmlspecialchars($current['context']) ?>
            </div>
            <div class="submission-divider"></div>
            <div class="submission-badges">
              <span class="submission-badge">Clearance: Internal</span>
              <span class="submission-badge">Retention: Indefinite</span>
              <span class="submission-badge">PII/PHI: Encrypted</span>
            </div>
          </aside>
        </div>
      </div>
    </div>
  </div>
