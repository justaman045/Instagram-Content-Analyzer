// ==========================================
// TELEGRAM -> GITHUB ACTIONS BRIDGE
// ==========================================
// Copy this code into script.google.com
// ==========================================

// 1. CONFIGURATION
const GITHUB_TOKEN = "YOUR_GITHUB_PAT_HERE"; // Generate at github.com/settings/tokens (Needs 'repo' scope)
const GITHUB_REPO = "justaman045/Instagram"; // Your Username/RepoName
const WORKFLOW_ID = "runner.yml";            // The filename of your workflow

const TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE";

// 2. MAIN WEBHOOK HANDLER
function doPost(e) {
    try {
        const update = JSON.parse(e.postData.contents);

        // Check if it's a message
        if (update.message) {
            const chatId = update.message.chat.id;
            const text = update.message.text || "";

            // OPTIONAL: Filter by user ID if you want to be exclusive
            // if (chatId !== 123456789) return;

            // 1. Acknowledge Receipt (Optional UI feedback)
            // sendMessage(chatId, "⏳ Waking up analysis bot...");

            // 2. Trigger GitHub Action
            triggerGitHubAction(chatId);
        }
    } catch (error) {
        // Log error silently
    }

    return ContentService.createTextOutput("OK");
}

// 3. TRIGGER GITHUB ACTION
function triggerGitHubAction(chatId) {
    const url = `https://api.github.com/repos/${GITHUB_REPO}/actions/workflows/${WORKFLOW_ID}/dispatches`;

    const payload = {
        ref: "main", // or master
        inputs: {
            runtime: "5" // Run for 5 minutes only
        }
    };

    const options = {
        method: "post",
        headers: {
            "Authorization": "Bearer " + GITHUB_TOKEN,
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Google-Apps-Script"
        },
        payload: JSON.stringify(payload)
    };

    UrlFetchApp.fetch(url, options);
}

// 4. TELEGRAM HELPER
function sendMessage(chatId, text) {
    const url = `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage`;
    const payload = {
        chat_id: chatId,
        text: text
    };
    const options = {
        method: "post",
        contentType: "application/json",
        payload: JSON.stringify(payload)
    };
    UrlFetchApp.fetch(url, options);
}
