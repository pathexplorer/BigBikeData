/**
 * @fileoverview Main entry point for the frontend application.
 * This file imports and initializes all application modules.
 */
import { initFileHandler } from './file_handler.js';

// --- Application Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    console.log("Application starting...");

    // Initialize the file handling module.
    // It now reads its configuration directly from the DOM.
    initFileHandler();

    // If the application grows, other modules (e.g., for analytics or modals)
    // would be initialized here.
});
