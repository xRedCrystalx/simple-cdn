"use strict";

/*
 * Shared helpers for the upload and admin pages.
 */

const REQUEST_TIMEOUT = 30_000;

function $(id) {
    return document.getElementById(id);
}

function setMessage(element, text, kind) {
    element.className = kind ? `message ${kind}` : "message";
    element.textContent = text || "";
}


function formatBytes(bytes) {
    const units = ["B", "KB", "MB", "GB", "TB"];

    let value = bytes;
    let unit = 0;

    while (value >= 1024 && unit < units.length - 1) {
        value /= 1024;
        unit += 1;
    }

    return `${value < 10 && unit > 0 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
}

function authHeaders(token, extra) {
    return Object.assign({ "Red-Authorization": `Token ${token}` }, extra || {});
}

async function requestJSON(url, options) {
    const response = await fetch(url, Object.assign(
        { signal: AbortSignal.timeout(REQUEST_TIMEOUT), credentials: "same-origin" },
        options
    ));

    let data = null;

    try {
        data = await response.json();
    }
    catch {
        data = null;
    }

    if (!response.ok) {
        throw new Error(errorMessage(data) || `Request failed (${response.status}).`);
    }

    if (data && data.status === "error") {
        throw new Error(data.message || "Request failed.");
    }

    return data;
}

function errorMessage(data) {
    if (!data) {
        return null;
    }

    if (typeof data.message === "string") {
        return data.message;
    }

    // fastapi raises HTTPException, which serialises to {"detail": ...}
    if (typeof data.detail === "string") {
        return data.detail;
    }

    return null;
}


/*
 * fetch() cannot report upload progress, so uploads go through XHR.
 * Resolves with the parsed StatusResponse, rejects with a plain Error.
 */
function uploadFile({ token, file, metadata, onProgress }) {
    return new Promise((resolve, reject) => {
        const body = new FormData();
        body.append("file", file);
        body.append("metadata", JSON.stringify(metadata));

        const xhr = new XMLHttpRequest();
        xhr.open("POST", "/api/files/", true);
        xhr.setRequestHeader("Red-Authorization", `Token ${token}`);
        xhr.responseType = "json";

        xhr.upload.addEventListener("progress", (event) => {
            if (event.lengthComputable && onProgress) {
                onProgress(event.loaded / event.total);
            }
        });

        xhr.addEventListener("load", () => {
            const data = xhr.response;

            if (xhr.status >= 400) {
                reject(new Error(errorMessage(data) || `Upload failed (${xhr.status}).`));
                return;
            }

            if (!data || data.status !== "success" || !data.data) {
                reject(new Error(errorMessage(data) || "Upload failed."));
                return;
            }

            resolve(data);
        });

        xhr.addEventListener("error", () => reject(new Error("Network error during upload.")));
        xhr.addEventListener("abort", () => reject(new Error("Upload cancelled.")));
        xhr.addEventListener("timeout", () => reject(new Error("Upload timed out.")));

        xhr.send(body);
    });
}


/* Renders `url` as a link, but only after confirming it is really an http(s) url. */
function renderLink(container, url) {
    container.textContent = "";

    let parsed = null;

    try {
        parsed = new URL(url, window.location.origin);
    }
    catch {
        container.textContent = String(url);
        return;
    }

    if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
        container.textContent = parsed.href;
        return;
    }

    const link = document.createElement("a");
    link.href = parsed.href;
    link.textContent = parsed.href;
    link.rel = "noreferrer";

    container.appendChild(link);
}

async function copyText(text, button) {
    const original = button.textContent;

    try {
        await navigator.clipboard.writeText(text);
        button.textContent = "Copied";
    }
    catch {
        button.textContent = "Copy failed";
    }

    setTimeout(() => { button.textContent = original; }, 1500);
}


/* Keeps a form locked while `action` runs so a double click cannot fire two uploads. */
async function withLock(button, label, action) {
    const original = button.textContent;

    button.disabled = true;
    button.textContent = label;

    try {
        await action();
    }
    finally {
        button.disabled = false;
        button.textContent = original;
    }
}

/* Wires drag and drop onto a <label class="drop-area"> that wraps a file input. */
function bindDropArea(area, input, onChange) {
    const update = () => onChange(input.files.length ? input.files[0] : null);

    for (const name of ["dragenter", "dragover", "dragleave", "drop"]) {
        area.addEventListener(name, (event) => {
            event.preventDefault();
            area.classList.toggle("dragging", name === "dragenter" || name === "dragover");
        });
    }

    area.addEventListener("drop", (event) => {
        const dropped = event.dataTransfer && event.dataTransfer.files;

        if (dropped && dropped.length) {
            const transfer = new DataTransfer();
            transfer.items.add(dropped[0]);

            input.files = transfer.files;
            update();
        }
    });

    input.addEventListener("change", update);
}
