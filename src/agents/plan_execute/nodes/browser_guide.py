"""Browser automation reliability guide inlined into browser task prompts."""

BROWSER_RELIABILITY_GUIDE = '''
ADVANCED BROWSER AUTOMATION RELIABILITY GUIDE
=============================================

This guide covers comprehensive test cases and reliability patterns for browser automation.
It addresses dynamic UI states, timing issues, overlays, and common failure modes.

---

## 1. OVERLAY AND MODAL HANDLING

### Date Pickers and Calendars
- Always verify that date selection is complete before proceeding
- After selecting a date, the calendar overlay must be fully dismissed
- Common patterns:
  * Click "Done" or "Apply" button (most common)
  * Click outside the calendar to dismiss
  * Press Enter/Escape key
  * Click a specific "OK" or "Confirm" button
- Verification steps:
  * Calendar element is no longer visible in DOM
  * Calendar has display: none or is hidden
  * The input field now shows the selected date
  * No date-related overlay is present

- Failure case: If calendar remains visible after click, the selection was not committed
- Always add explicit wait for calendar dismissal before next action

### Dropdowns and Select Menus
- Single-select dropdowns:
  * Click dropdown to open
  * Select option (click or arrow keys + Enter)
  * Verify dropdown is closed
  * Verify selected value is displayed in trigger element
  * Verify underlying form value is updated

- Multi-select dropdowns:
  * Click to open
  * Select multiple options
  * Look for "Done", "Apply", or "Confirm" button
  * Click confirmation button
  * Verify dropdown is closed
  * Verify all selected values are displayed

- Custom/autocomplete dropdowns:
  * Type in search field
  * Wait for suggestions to appear (explicit wait)
  * Select from suggestions
  * Verify selection is applied
  * Verify dropdown closes automatically or manually close it

- Verification:
  * Dropdown container is hidden/removed
  * ARIA expanded attribute is false
  * No dropdown menu is visible in viewport
  * Selected value is reflected in UI

### Modals and Dialogs
- Action modals (confirm, delete, save):
  * Identify primary action button
  * Identify cancel/dismiss button
  * After clicking action, verify modal is dismissed
  * Verify expected page state change occurred
  * Verify success/error message if applicable

- Form modals:
  * Fill all required fields
  * Handle validation errors if present
  * Click submit/save
  * Verify modal closes
  * Verify data is persisted
  * Verify confirmation message appears

- Informational modals:
  * Click close (X) button
  * Click outside modal (if dismissible)
  * Press Escape key
  * Verify modal is removed from DOM

- Verification:
  * Modal overlay is gone
  * Modal content is hidden/removed
  * Page scrolling is re-enabled (if blocked by modal)
  * Focus returns to triggering element

### Toasts and Notifications
- Success toasts:
  * Wait for toast to appear
  * Read message for verification
  * Wait for auto-dismiss or manually dismiss
  * Verify toast is removed from DOM

- Error toasts:
  * Capture error message
  * Check for retry/action buttons
  * Dismiss if needed
  * Verify underlying error state is resolved

- Persistent notifications:
  * Check for close button
  * Check if auto-dismiss is available
  * Dismiss before proceeding if it blocks UI

---

## 2. FORM SUBMISSION AND CONFIRMATION

### Submit Buttons and Forms
- Never consider a click successful based solely on click execution
- Verification hierarchy:
  1. URL changed (navigation occurred)
  2. Page content updated (new data displayed)
  3. Success message appeared
  4. Form cleared/reset
  5. Loading state completed

- Multi-step forms:
  * Verify each step completion before proceeding
  * Check for progress indicators
  * Verify step-specific validation
  * Handle "Back", "Next", "Submit" appropriately

- AJAX form submissions:
  * Wait for loading spinner to complete
  * Wait for success/error response
  * Verify DOM update occurred
  * Check network request completion if accessible

### Search and Filter Actions
- Search input:
  * Type search query
  * Click search button or press Enter
  * Wait for results to load
  * Verify results are displayed
  * Verify URL contains search parameters (if applicable)

- Filter applications:
  * Select filter criteria
  * Apply filter (explicit button or auto-apply)
  * Wait for filtered results
  * Verify results match filter criteria
  * Verify filter UI shows active state

- Verification failures:
  * If no results appear, check for "no results" message
  * If results don't change, filter may not have applied
  * If loading persists, may be timeout or error

---

## 3. AUTHENTICATION AND LOGIN HANDLING

### Login Popups and Modals
- Unexpected login popups:
  * Click close (X) button immediately
  * Verify popup is dismissed
  * Verify main content is accessible
  * If popup reappears, content may require auth

- Required authentication:
  * If login is requested repeatedly after dismissal:
    * End task with: "Cannot execute - authentication required"
    * Do not attempt to bypass auth
    * Do not enter credentials unless explicitly provided

- Auth flows:
  * Identify if auth is truly required vs. optional
  * Check for "continue as guest" options
  * Check for social login alternatives
  * Only proceed with auth if credentials are provided

### Session Management
- Session timeouts:
  * Detect session expiry messages
  * Check for redirect to login
  * Handle session refresh if possible
  * Report session loss if blocking task

- Logout scenarios:
  * Identify logout triggers
  * Handle session termination gracefully
  * Report if logout prevents task completion

---

## 4. DYNAMIC CONTENT AND LOADING STATES

### Loading States and Spinners
- Always wait for loading states to complete:
  * Loading spinners
  * Skeleton screens
  * Progress bars
  * "Loading..." text

- Verification:
  * Loading element is removed from DOM
  * Loading element is hidden (display: none)
  * Content is actually visible
  * No loading indicators remain

- Timeout handling:
  * Set reasonable timeout for loading
  * If timeout exceeded, check for errors
  * Report loading failure if content never appears

### AJAX and Async Content
- Content loaded via AJAX:
  * Wait for network request completion
  * Wait for DOM update
  * Verify new content is visible
  * Verify old content is replaced/updated

- Infinite scroll:
  * Scroll to trigger load
  * Wait for new content to appear
  * Verify content increment
  * Repeat until target reached or end detected

- Lazy-loaded images:
  * Scroll element into view
  * Wait for image to load
  * Verify image src is updated
  * Verify image is visible

### Client-Side Routing (SPAs)
- URL changes without page reload:
  * Wait for URL to update
  * Wait for content transition
  * Verify new route is active
  * Verify route-specific content appears

- Back/forward navigation:
  * Use browser navigation controls
  * Wait for route to restore
  * Verify state is preserved
  * Verify content matches expected route

---

## 5. ELEMENT STATE VERIFICATION

### Visibility and Display
- Element not visible ≠ element not present:
  * Check element.exists() vs element.is_visible()
  * Hidden elements may still be in DOM
  * Consider CSS display, visibility, opacity
  * Check for element being outside viewport

- Element obscured by other elements:
  * Check z-index stacking
  * Check for overlapping elements
  * Scroll element into view if needed
  * Verify element is clickable

### Enabled/Disabled States
- Disabled form elements:
  * Check disabled attribute
  * Check aria-disabled attribute
  * Check visual styling (grayed out)
  * Do not attempt interaction with disabled elements

- Read-only elements:
  * Check readonly attribute
  * Verify value cannot be changed
  * Look for edit buttons/controls
  * Enable editing if UI provides mechanism

### Interactive Elements
- Clickable elements:
  * Verify element is not disabled
  * Verify element is not obscured
  * Verify element is in viewport
  * Check for pointer-events CSS

- Hover states:
  * Trigger hover action
  * Wait for hover content to appear
  * Verify hover menu/tooltip is visible
  * Dismiss hover if needed

---

## 6. TIMING AND RACE CONDITIONS

### Explicit Waits vs. Sleeps
- Never use fixed sleep times when possible
- Use explicit waits for specific conditions:
  * Element visibility
  * Element clickability
  * Text presence
  * Attribute changes
  * URL changes

- Dynamic timeouts:
  * Set reasonable maximum timeouts
  * Adjust based on expected operation duration
  * Consider network conditions
  * Consider server load

### Debounce and Throttle
- Debounced inputs (search, autocomplete):
  * Wait for debounce delay after typing
  * Typical delays: 300ms, 500ms
  * Verify suggestions/results appear
  * Adjust timing if too fast/slow

- Throttled actions (scroll, resize):
  * Wait for throttle interval
  * Verify action is processed
  * Check for visual feedback

### Animation Completion
- CSS animations:
  * Wait for animation to complete
  * Check for animation-end events
  * Verify final state is reached
  * Consider animation duration

- Transitions:
  * Wait for transition to complete
  * Verify end state
  * Check for transition-end events

---

## 7. ERROR HANDLING AND RECOVERY

### Network Errors
- Failed requests:
  * Check for error messages
  * Check for error toasts
  * Check for HTTP error codes
  * Attempt retry if appropriate

- Timeouts:
  * Increase timeout if reasonable
  * Check for slow network conditions
  * Report timeout if unresolvable

### Element Not Found
- Temporary absence:
  * Wait for element to appear
  * Check for dynamic loading
  * Verify selector is correct

- Permanent absence:
  * Verify element should exist
  * Check for alternative selectors
  * Check for page layout changes
  * Report if element is missing unexpectedly

### Stale Element References
- DOM updates:
  * Re-locate element after DOM change
  * Use stable selectors (IDs, data attributes)
  * Avoid fragile selectors (nth-child, arbitrary classes)

- Re-query strategy:
  * Store locator, not element reference
  * Re-query before each interaction
  * Handle element recreation

---

## 8. FORM VALIDATION AND INPUT

### Required Fields
- Identify required fields:
  * Check for required attribute
  * Check for asterisk (*) indicator
  * Check for validation messages

- Handle validation:
  * Fill all required fields
  * Trigger validation (blur, submit attempt)
  * Clear validation errors if present
  * Proceed only when valid

### Input Types
- Text inputs:
  * Clear existing value before typing
  * Handle character limits
  * Handle special characters
  * Verify input value after entry

- Number inputs:
  * Verify min/max constraints
  * Handle step increments
  * Check for validation errors

- File inputs:
  * Use file upload method if available
  * Verify file is selected
  * Check for file size limits
  * Verify file type restrictions

### Auto-complete and Suggestions
- Trigger suggestions:
  * Type partial input
  * Wait for suggestions to appear
  * Select from suggestions
  * Verify selection is applied

- Handle suggestion dismissal:
  * Click outside to dismiss
  * Press Escape
  * Verify no suggestion is selected

---

## 9. NAVIGATION AND ROUTING

### Page Loads
- Full page loads:
  * Wait for document ready
  * Wait for main content
  * Verify expected URL
  * Verify page title

- Partial loads:
  * Wait for specific content
  * Verify update occurred
  * Check for loading indicators

### New Tabs and Windows
- New tab handling:
  * Switch to new tab
  * Wait for content load
  * Perform actions in new tab
  * Switch back to original tab if needed

- Window management:
  * Handle multiple windows
  * Close windows when done
  * Verify correct window is active

### Back and Forward Navigation
- Browser navigation:
  * Use back/forward buttons
  * Wait for page to restore
  * Verify state is preserved
  * Handle form resubmission warnings

---

## 10. CROSS-BROWSER AND RESPONSIVE CONSIDERATIONS

### Viewport and Responsive Design
- Different screen sizes:
  * Test at various viewport sizes
  * Handle mobile layouts
  * Handle desktop layouts
  * Check for responsive breakpoints

- Mobile-specific:
  * Handle hamburger menus
  * Handle touch interactions
  * Handle mobile-specific controls

### Browser-Specific Behavior
- Different browsers:
  * Test in target browsers
  * Handle browser-specific quirks
  * Verify consistent behavior

- Browser settings:
  * Handle pop-up blockers
  - Handle ad blockers
  - Handle JavaScript disabled scenarios

---

## 11. VERIFICATION PATTERNS

### Positive Verification
- Confirm expected state:
  * Element is visible
  * Text is present
  * Attribute has expected value
  * URL matches pattern

### Negative Verification
- Confirm absence:
  * Element is not visible
  * Text is not present
  * Error message is absent
  * Loading is complete

### State Transition Verification
- Before/after comparison:
  * Capture initial state
  * Perform action
  * Capture final state
  * Verify expected changes

---

## 12. COMMON PITFALLS AND SOLUTIONS

### False Positives
- Click executed but not effective:
  * Always verify post-click state
  * Check for overlay blocking
  * Check for element recreation

### Timing Issues
- Race conditions:
  * Use explicit waits
  * Avoid fixed sleeps
  * Handle async operations

### Fragile Selectors
- Unreliable locators:
  * Use stable selectors
  * Prefer IDs and data attributes
  - Avoid dynamic classes
  - Avoid positional selectors

---

## IMPLEMENTATION CHECKLIST

Before marking any step as complete, verify:
- [ ] Overlays/modals are dismissed
- [ ] Loading states are complete
- [ ] Expected content is visible
- [ ] Form values are updated
- [ ] URL changed (if navigation expected)
- [ ] Success/error messages handled
- [ ] No unexpected popups appeared
- [ ] Element is in viewport
- [ ] Element is not obscured
- [ ] Element is enabled/clickable
- [ ] Authentication not required (or handled)
- [ ] Network requests completed
- [ ] Animations/transitions finished
- [ ] Dynamic content loaded
- [ ] Validation passed (if applicable)


"""

'''
