/**
 * @fileoverview Utility functions for the application.
 * This module exports general functions that are decoupled from the DOM.
 */

/**
 * Formats a file size in bytes to a human-readable string (e.g., 10.5 KB, 2.3 MB).
 * @param {number} bytes - The file size in bytes.
 * @returns {string} The human-readable file size string.
 */
export function formatFileSize(bytes) {
    if (typeof bytes !== 'number' || bytes < 0) {
        console.error("Invalid bytes value provided to formatFileSize.");
        return '0 Bytes';
    }
    if (bytes === 0) {
        return '0 Bytes';
    }
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    // Use Math.max(0, i) to ensure we don't use a negative index, though unlikely with the check above.
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}