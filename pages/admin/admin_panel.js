"use strict";

/*
 * ADMIN_TOKEN is defined by the page just above this script. It lives in memory for as
 * long as the document does and is never written to storage.
 */

let createdTokenValue = "";
let managedFileUrl = "";


/* Statistics */
const statsMessage = $("statsMessage");

function renderStats(data) {
    $("statUploads").textContent = data.total_uploads;
    $("statScreenshots").textContent = data.total_screenshots;
    $("statTokens").textContent = data.total_admin_tokens;
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

$("refreshStats").addEventListener("click", loadStats);


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
const createMessage = $("createMessage");
const createResult = $("createResult");

$("createForm").addEventListener("submit", async (event) => {
    event.preventDefault();

    setMessage(createMessage, "");
    createResult.hidden = true;

    const userId = parseInt($("createUserId").value, 10);

    if (!Number.isInteger(userId) || userId < 1) {
        setMessage(createMessage, "Enter a valid user ID.", "error");
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
