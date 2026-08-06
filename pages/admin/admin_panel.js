"use strict";

/*
 * ADMIN_TOKEN is defined by the page just above this script. It lives in memory for as
 * long as the document does and is never written to storage.
 */

const GIGABYTE = 1024 ** 3;

let createdTokenValue = "";
let managedFileUrl = "";


/* Statistics */
const statsMessage = $("statsMessage");

function renderStats(data) {
    $("statUploads").textContent = data.total_uploads;
    $("statScreenshots").textContent = data.total_screenshots;
    $("statTokens").textContent = data.total_admin_tokens;

    // The api reports the disk in gigabytes, formatBytes() wants bytes.
    $("statStorage").textContent = formatBytes(data.used_storage * GIGABYTE) + " / " + formatBytes(data.total_storage * GIGABYTE);
    $("statFree").textContent = formatBytes((data.total_storage - data.used_storage) * GIGABYTE);
}

async function loadStats() {
    await withLock($("refreshStats"), "Loading...", async () => {
        setMessage(statsMessage, "");

        try {
            renderStats(await requestJSON("/api/admin/stats", { headers: authHeaders(ADMIN_TOKEN) }));
        }
        catch (error) {
            setMessage(statsMessage, error.message, "error");
        }
    });
}

// Accounts are created outside the panel, so a refresh picks those up as well as the counters.
$("refreshStats").addEventListener("click", () => Promise.all([loadStats(), loadUsers()]));


/* Managed upload */
const managedFolder = $("managedFolder");
const managedFile = $("managedFile");
const managedMessage = $("managedMessage");
const managedPreview = $("managedPreview");
const managedResult = $("managedResult");
const managedProgress = $("managedProgress");
const managedBar = $("managedBar");

const managedEmptyName = $("managedName").textContent;
const managedEmptyMeta = $("managedMeta").textContent;

function updatePreview() {
    const file = managedFile.files[0];

    if (!file) {
        managedPreview.textContent = "";
        return;
    }

    const folder = managedFolder.value.trim().replace(/^\/+|\/+$/g, "");
    managedPreview.textContent = `Will be served at /${folder ? `${folder}/` : ""}${file.name}`;
}

bindDropArea($("managedDrop"), managedFile, (file) => {
    $("managedName").textContent = file ? file.name : managedEmptyName;
    $("managedMeta").textContent = file ? formatBytes(file.size) : managedEmptyMeta;

    updatePreview();
});

managedFolder.addEventListener("input", updatePreview);

$("managedForm").addEventListener("submit", async (event) => {
    event.preventDefault();

    setMessage(managedMessage, "");
    managedResult.hidden = true;

    const file = managedFile.files[0];

    if (!file) {
        setMessage(managedMessage, "Select a file first.", "error");
        return;
    }

    managedProgress.hidden = false;
    managedBar.style.width = "0%";

    await withLock($("managedButton"), "Uploading...", async () => {
        try {
            setMessage(managedMessage, "Uploading...");

            const data = await uploadFile({
                token: ADMIN_TOKEN,
                file: file,
                metadata: {
                    type: "admin",
                    protected: null,
                    extra: managedFolder.value || null
                },
                onProgress: (fraction) => { managedBar.style.width = `${Math.round(fraction * 100)}%`; }
            });

            managedFileUrl = String(data.data.url || "");

            setMessage(managedMessage, "Upload complete.", "success");
            renderLink($("managedUrl"), managedFileUrl);

            managedResult.hidden = false;

            managedFile.value = "";
            $("managedName").textContent = managedEmptyName;
            $("managedMeta").textContent = managedEmptyMeta;
            managedPreview.textContent = "";
        }
        catch (error) {
            setMessage(managedMessage, error.message, "error");
        }
        finally {
            managedProgress.hidden = true;
            managedBar.style.width = "0%";
        }
    });
});

$("managedCopy").addEventListener("click", () => copyText(managedFileUrl, $("managedCopy")));


/* Create token */
const createUser = $("createUser");
const createMessage = $("createMessage");
const createResult = $("createResult");

/*
 * The picker shows usernames, the api only ever deals in account ids, so every option
 * carries its id as the value and the id is what leaves the page.
 */
async function loadUsers() {
    // A reload rebuilds the list from scratch, so hold on to whoever was picked.
    const selected = createUser.value;

    createUser.textContent = "";
    createUser.disabled = true;

    const placeholder = (label) => { createUser.appendChild(new Option(label, "")); };

    try {
        const data = await requestJSON("/api/admin/users", { headers: authHeaders(ADMIN_TOKEN) });
        const users = data.users || [];

        if (!users.length) {
            placeholder("No accounts");
            setMessage(createMessage, "No accounts exist yet, create one with create_user.py.", "error");
            return;
        }

        for (const user of users) {
            createUser.appendChild(new Option(user.username, String(user.id)));
        }

        // Falls back to the first account when that user is gone, value goes empty on a miss.
        createUser.value = selected;

        if (!createUser.value) {
            createUser.selectedIndex = 0;
        }

        createUser.disabled = false;
    }
    catch (error) {
        placeholder("Could not load users");
        setMessage(createMessage, error.message, "error");
    }
}

$("createForm").addEventListener("submit", async (event) => {
    event.preventDefault();

    setMessage(createMessage, "");
    createResult.hidden = true;

    const userId = parseInt(createUser.value, 10);

    if (!Number.isInteger(userId) || userId < 1) {
        setMessage(createMessage, "Select a user first.", "error");
        return;
    }

    await withLock($("createButton"), "Creating...", async () => {
        try {
            const data = await requestJSON("/api/admin/token", {
                method: "POST",
                headers: authHeaders(ADMIN_TOKEN, { "Content-Type": "application/json" }),
                body: JSON.stringify({ user_id: userId, type: $("createType").value })
            });

            createdTokenValue = String(data.token || "");

            $("createdToken").textContent = createdTokenValue;
            createResult.hidden = false;

            setMessage(createMessage, "Copy it now, it is not shown again.", "success");
        }
        catch (error) {
            setMessage(createMessage, error.message, "error");
        }
    });
});

$("createCopy").addEventListener("click", () => copyText(createdTokenValue, $("createCopy")));


/* Delete token */
const deleteMessage = $("deleteMessage");

$("deleteForm").addEventListener("submit", async (event) => {
    event.preventDefault();

    setMessage(deleteMessage, "");

    const target = $("deleteToken").value.trim();
    const rawUserId = $("deleteUserId").value.trim();
    const userId = rawUserId ? parseInt(rawUserId, 10) : null;

    if (!target && userId === null) {
        setMessage(deleteMessage, "Provide either a token or a user ID.", "error");
        return;
    }

    if (target && userId !== null) {
        setMessage(deleteMessage, "Provide either a token or a user ID, not both.", "error");
        return;
    }

    if (!window.confirm(target ? "Delete this token?" : `Delete every token of user ${userId}?`)) {
        return;
    }

    await withLock($("deleteButton"), "Deleting...", async () => {
        try {
            const data = await requestJSON("/api/admin/token", {
                method: "DELETE",
                headers: authHeaders(ADMIN_TOKEN, { "Content-Type": "application/json" }),
                body: JSON.stringify({ token: target || null, user_id: userId })
            });

            setMessage(deleteMessage, data.message || "Deleted.", "success");
            $("deleteForm").reset();
        }
        catch (error) {
            setMessage(deleteMessage, error.message, "error");
        }
    });
});


/* Delete file */
const fileMessage = $("fileMessage");

$("fileForm").addEventListener("submit", async (event) => {
    event.preventDefault();

    setMessage(fileMessage, "");

    const endpoint = $("fileEndpoint").value.trim().replace(/^\/+/, "");

    if (!endpoint) {
        setMessage(fileMessage, "Enter an endpoint.", "error");
        return;
    }

    await withLock($("fileButton"), "Deleting...", async () => {
        try {
            const data = await requestJSON("/api/files/", {
                method: "DELETE",
                headers: authHeaders(ADMIN_TOKEN, { "Content-Type": "application/json" }),
                body: JSON.stringify({ endpoint: endpoint, protected: null })
            });

            setMessage(fileMessage, data.message || "Deleted.", "success");
            $("fileForm").reset();
        }
        catch (error) {
            setMessage(fileMessage, error.message, "error");
        }
    });
});


loadStats();
loadUsers();
