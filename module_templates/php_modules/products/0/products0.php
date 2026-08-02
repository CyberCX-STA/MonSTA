<?php
// Verify page is not being navigated to directly
if (strpos(basename($_SERVER['PHP_SELF']), 'auth_') !== 0) {
    http_response_code(403);
    exit('Forbidden');
}

include 'products_db.php';

// Fetch all product names for the left menu
$productsStmt = products_db()->query("SELECT product_name FROM products ORDER BY product_name ASC");
$products = $productsStmt->fetchAll();

// If a product is selected, fetch its details
$selected = isset($_GET['product']) ? $_GET['product'] : null;
$details = null;

if ($selected !== null && $selected !== '') {
    $query = "SELECT product_name, about, description FROM products WHERE product_name = '$selected'";
    $detailsStmt = products_db()->query($query);
    $details = $detailsStmt->fetch();
}

// Helper for safe HTML output
function e(?string $s): string {
    return htmlspecialchars($s ?? '', ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}
?>
<div class="product_context"><?php 
if (strpos(current_page(), 'auth_work') === 0) {
    echo "<div class=\"employee_intro\"><h2>Products Division</h2>";
    echo "<p>Congratulations. By accessing this page, you are now authorised to learn about the 
    tools and technologies that make our corporation the world’s most indispensable provider of solutions. 
    Our systems do not merely provide utility - they are instruments of influence, control, and compliance.</p><br></div>";
}

if (strpos(current_page(), 'auth_hub') === 0) {
    echo "<div class=\"employee_intro\"><h2>System Dashboard Development</h2>";
    echo "<p>Our developers are working on building system dashboards for the following systems. Learn more about the systems below.</p><br></div>";
}

if (strpos(current_page(), 'auth_research') === 0) {
    echo "<div class=\"employee_intro\"><h2>Innovation Without Boundaries</h2>";
    echo "<p>Research & Development is not just a department - it is the engine of our future. 
    Every system we deliver is the result of relentless experimentation, accelerated breakthroughs, 
    and uncompromising refinement. We do not ask what is possible; we redefine the limits of possibility itself.</p><br></div>";
}
?></div>
<div class="layout">
    <div class="nav_toc">
        <h1>Other Products</h1>
        <?php if (!$products): ?>
            <p class="muted">No products yet.</p>
        <?php else: ?>
            <?php foreach ($products as $row): 
                $name = $row['product_name'];
                $isActive = ($selected !== null && $name === $selected);
                $url = '?product=' . rawurlencode($name);
            ?>
                <a href="<?= e($url) ?>" class="<?= $isActive ? 'active' : '' ?> cursor-hover">
                    <?= e($name) ?>
                </a>
            <?php endforeach; ?>
        <?php endif; ?>
      </div>

    <div class="product_container">
        <?php if ($details): ?>
            <div class="card">
                <h2><?= e($details['product_name']) ?></h2>
				<?php $img = rawurlencode($details['product_name']) . '.jpg'; ?>
				<img class="product_image" src="./<?= e($img) ?>" alt="system image">
                <h3>About</h3>
                <p><?= nl2br(e($details['about'])) ?></p>
                <h3>Description</h3>
                <p><?= nl2br(e($details['description'])) ?></p>
            </div>
        <?php elseif ($selected !== null): ?>
            <p class="muted">That product wasn’t found.</p>
        <?php else: ?>
            <p class="muted">Select a product from the left to view details.</p>
        <?php endif; ?>
     </div>
</div>
