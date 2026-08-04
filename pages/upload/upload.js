"use strict";

const form = $("uploadForm");
const tokenInput = $("token");
const passwordInput = $("password");
const typeInput = $("type");

const fileInput = $("file");
const fileName = $("fileName");
const fileMeta = $("fileMeta");

const progress = $("progress");
const progressBar = $("progressBar");

const button = $("uploadButton");
const statusBox = $("status");
const result = $("result");
const resultUrl = $("resultUrl");
const copyButton = $("copyButton");

const emptyName = fileName.textContent;
const emptyMeta = fileMeta.textContent;

let uploadedUrl = "";


bindDropArea($("dropArea"), fileInput, (file) => {
    fileName.textContent = file ? file.name : emptyName;
    fileMeta.textContent = file ? formatBytes(file.size) : emptyMeta;
});


function setProgress(fraction) {
    progress.hidden = false;
    progressBar.style.width = `${Math.round(fraction * 100)}%`;
}


form.addEventListener("submit", async (event) => {
    event.preventDefault();

    setMessage(statusBox, "");
    result.hidden = true;

    const token = tokenInput.value.trim();

    if (!token) {
        setMessage(statusBox, "Enter your token first.", "error");
        tokenInput.focus();

        return;
    }

    const file = fileInput.files[0];

    if (!file) {
        setMessage(statusBox, "Select a file first.", "error");
        return;
    }

    setProgress(0);

    await withLock(button, "Uploading...", async () => {
        try {
            setMessage(statusBox, "Uploading...");

            const data = await uploadFile({
                token: token,
                file: file,
                metadata: {
                    type: typeInput.value,
                    protected: passwordInput.value || null,
                    extra: null
                },
                onProgress: setProgress
            });

            uploadedUrl = String(data.data.url || "");

            setMessage(statusBox, "Upload complete.", "success");
            renderLink(resultUrl, uploadedUrl);

            result.hidden = false;
            form.reset();

            fileName.textContent = emptyName;
            fileMeta.textContent = emptyMeta;
        }
        catch (error) {
            setMessage(statusBox, error.message, "error");
        }
        finally {
            progress.hidden = true;
            progressBar.style.width = "0%";
        }
    });
});


copyButton.addEventListener("click", () => copyText(uploadedUrl, copyButton));
