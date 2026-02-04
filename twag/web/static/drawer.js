/**
 * Drawer controller for mobile filter panel
 * Handles open/close, swipe-to-close, and keyboard navigation
 */
(function() {
    'use strict';

    const SWIPE_THRESHOLD = 50;
    const SWIPE_VELOCITY_THRESHOLD = 0.3;

    let drawer = null;
    let overlay = null;
    let toggleBtn = null;
    let closeBtn = null;
    let startX = 0;
    let startY = 0;
    let currentX = 0;
    let isDragging = false;
    let startTime = 0;

    function init() {
        drawer = document.getElementById('filter-drawer');
        overlay = document.getElementById('drawer-overlay');
        toggleBtn = document.getElementById('filter-toggle-btn');
        closeBtn = document.getElementById('drawer-close-btn');

        if (!drawer || !overlay) return;

        // Toggle button
        if (toggleBtn) {
            toggleBtn.addEventListener('click', toggle);
        }

        // Close button
        if (closeBtn) {
            closeBtn.addEventListener('click', close);
        }

        // Overlay click to close
        overlay.addEventListener('click', close);

        // Keyboard: Escape to close
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && isOpen()) {
                close();
            }
        });

        // Touch events for swipe-to-close
        drawer.addEventListener('touchstart', handleTouchStart, { passive: true });
        drawer.addEventListener('touchmove', handleTouchMove, { passive: false });
        drawer.addEventListener('touchend', handleTouchEnd, { passive: true });

        // Prevent body scroll when drawer is open
        drawer.addEventListener('touchmove', function(e) {
            if (isDragging) {
                e.preventDefault();
            }
        }, { passive: false });
    }

    function isOpen() {
        return drawer && drawer.classList.contains('is-open');
    }

    function open() {
        if (!drawer || !overlay) return;

        drawer.classList.add('is-open');
        overlay.classList.add('is-open');
        overlay.setAttribute('aria-hidden', 'false');

        if (toggleBtn) {
            toggleBtn.setAttribute('aria-expanded', 'true');
        }

        // Trap focus in drawer
        const firstFocusable = drawer.querySelector('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
        if (firstFocusable) {
            firstFocusable.focus();
        }

        // Prevent body scroll
        document.body.style.overflow = 'hidden';
    }

    function close() {
        if (!drawer || !overlay) return;

        drawer.classList.remove('is-open');
        overlay.classList.remove('is-open');
        overlay.setAttribute('aria-hidden', 'true');
        drawer.style.transform = '';

        if (toggleBtn) {
            toggleBtn.setAttribute('aria-expanded', 'false');
            toggleBtn.focus();
        }

        // Restore body scroll
        document.body.style.overflow = '';
    }

    function toggle() {
        if (isOpen()) {
            close();
        } else {
            open();
        }
    }

    function handleTouchStart(e) {
        if (!isOpen()) return;

        const touch = e.touches[0];
        startX = touch.clientX;
        startY = touch.clientY;
        currentX = startX;
        startTime = Date.now();
        isDragging = false;
    }

    function handleTouchMove(e) {
        if (!isOpen()) return;

        const touch = e.touches[0];
        const deltaX = touch.clientX - startX;
        const deltaY = touch.clientY - startY;

        // Only start dragging if horizontal movement is greater than vertical
        if (!isDragging) {
            if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > 10) {
                isDragging = true;
            } else {
                return;
            }
        }

        currentX = touch.clientX;

        // Only allow dragging to the left (closing direction)
        if (deltaX < 0) {
            e.preventDefault();
            drawer.style.transform = `translateX(${deltaX}px)`;
            drawer.style.transition = 'none';

            // Fade overlay based on drag distance
            const drawerWidth = drawer.offsetWidth;
            const progress = Math.min(1, Math.abs(deltaX) / drawerWidth);
            overlay.style.opacity = 1 - progress;
        }
    }

    function handleTouchEnd(e) {
        if (!isDragging || !isOpen()) {
            isDragging = false;
            return;
        }

        isDragging = false;
        drawer.style.transition = '';
        overlay.style.opacity = '';

        const deltaX = currentX - startX;
        const deltaTime = Date.now() - startTime;
        const velocity = Math.abs(deltaX) / deltaTime;

        // Close if swiped far enough or fast enough
        if (deltaX < -SWIPE_THRESHOLD || (deltaX < 0 && velocity > SWIPE_VELOCITY_THRESHOLD)) {
            close();
        } else {
            // Snap back
            drawer.style.transform = '';
        }
    }

    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Expose to global scope for external control
    window.filterDrawer = {
        open: open,
        close: close,
        toggle: toggle,
        isOpen: isOpen
    };
})();
