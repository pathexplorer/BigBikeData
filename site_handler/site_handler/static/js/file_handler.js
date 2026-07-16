/**
 * @fileoverview Handles file input change and form submission logic.
 * This module manages DOM interaction and state changes for the file upload form.
 * It depends on the reusable formatFileSize utility.
 */
import { formatFileSize } from './utils.js';

// DOM Element references (module-level constants)
const fileInput = document.getElementById('fit_file');
const selectText = document.getElementById('select-text');
const dragDropText = document.getElementById('drag-drop-text');
const fileRestrictions = document.getElementById('file-restrictions');
const uploadIcon = document.getElementById('upload-icon');
const fileDisplayBox = document.getElementById('file-display-box');
const submitBtn = document.getElementById('submit-btn');
const uploadForm = document.getElementById('upload-form');

/**
 * Updates the UI based on the selected file.
 * @param {FileList | null} files - The list of files selected from the input.
 */
function updateFileDisplay(files) {
    // Check if files is valid and has at least one file
    if (files && files.length > 0) {
        const file = files[0];
        // 1. Update text content
        selectText.textContent = file.name;
        dragDropText.textContent = ` (${formatFileSize(file.size)})`;
        // Read the "ready" text from the data attribute
        fileRestrictions.textContent = fileRestrictions.dataset.readyText;

        // 2. Apply success/active styling
        selectText.classList.add('text-gray-900', 'font-bold');
        dragDropText.classList.add('text-gray-900', 'font-medium');
        dragDropText.classList.remove('pl-1');
        uploadIcon.classList.remove('text-gray-400');
        uploadIcon.classList.add('text-indigo-600');
        fileDisplayBox.classList.remove('border-gray-300');
        fileDisplayBox.classList.add('border-indigo-500', 'bg-indigo-50/50');
        fileRestrictions.classList.remove('text-gray-500');
        fileRestrictions.classList.add('text-green-600');
    } else {
        // Reset to default state by reading from data attributes
        selectText.textContent = selectText.dataset.defaultText;
        dragDropText.textContent = dragDropText.dataset.defaultText;
        fileRestrictions.textContent = fileRestrictions.dataset.defaultText;

        // Reset styling
        selectText.classList.remove('text-gray-900', 'font-bold');
        dragDropText.classList.remove('text-gray-900', 'font-medium');
        dragDropText.classList.add('pl-1');
        uploadIcon.classList.add('text-gray-400');
        uploadIcon.classList.remove('text-indigo-600');
        fileDisplayBox.classList.add('border-gray-300');
        fileDisplayBox.classList.remove('border-indigo-500', 'bg-indigo-50/50');
        fileRestrictions.classList.add('text-gray-500');
        fileRestrictions.classList.remove('text-green-600');
    }
}

/**
 * Initializes the file input listener.
 */
function initFileInput() {
    if (fileInput) {
        // Add change listener to the file input.
        // This will only trigger on user interaction.
        fileInput.addEventListener('change', (e) => updateFileDisplay(e.target.files));

        // DO NOT call updateFileDisplay on initial load.
        // The server has already rendered the correct default state.
    } else {
        console.error("File input element (fit_file) not found.");
    }
}

/**
 * Initializes the form submission prevention logic (for idempotency).
 */
function initFormSubmission() {
    if (uploadForm && submitBtn) {
        uploadForm.addEventListener('submit', function() {
            // Disable the button to prevent multiple clicks
            submitBtn.disabled = true;
            // Change the button text to give user feedback
            submitBtn.textContent = submitBtn.dataset.processingText;
        });
    } else {
        console.error("Upload form or submit button not found.");
    }
}

/**
 * Main initialization function for the file handler module.
 */
export function initFileHandler() {
    // Initialize all listeners
    initFileInput();
    initFormSubmission();
}
