/**
 * Modal controller with mobile bottom sheet behavior
 * Handles swipe-to-dismiss on mobile devices
 */
(function() {
    'use strict';

    const SWIPE_THRESHOLD = 100;
    const SWIPE_VELOCITY_THRESHOLD = 0.5;

    let activeModal = null;
    let modalCard = null;
    let startY = 0;
    let currentY = 0;
    let isDragging = false;
    let startTime = 0;

    function init() {
        // Find all modals and attach handlers
        document.querySelectorAll('.modal').forEach(function(modal) {
            const card = modal.querySelector('.modal-card');
            if (!card) return;

            // Add drag handle for mobile
            if (!card.querySelector('.modal-drag-handle')) {
                const handle = document.createElement('div');
                handle.className = 'modal-drag-handle';
                handle.setAttribute('aria-hidden', 'true');
                card.insertBefore(handle, card.firstChild);
            }

            // Touch events for swipe-to-dismiss
            card.addEventListener('touchstart', handleTouchStart, { passive: true });
            card.addEventListener('touchmove', handleTouchMove, { passive: false });
            card.addEventListener('touchend', handleTouchEnd, { passive: true });
        });
    }

    function isMobile() {
        return window.innerWidth < 768;
    }

    function handleTouchStart(e) {
        if (!isMobile()) return;

        const modal = e.currentTarget.closest('.modal');
        if (!modal || !modal.classList.contains('flex')) return;

        activeModal = modal;
        modalCard = e.currentTarget;

        const touch = e.touches[0];
        startY = touch.clientY;
        currentY = startY;
        startTime = Date.now();
        isDragging = false;
    }

    function handleTouchMove(e) {
        if (!activeModal || !modalCard || !isMobile()) return;

        const touch = e.touches[0];
        const deltaY = touch.clientY - startY;

        // Only allow dragging downward
        if (deltaY < 0) return;

        // Start dragging after small threshold
        if (!isDragging && deltaY > 10) {
            isDragging = true;
        }

        if (!isDragging) return;

        currentY = touch.clientY;
        e.preventDefault();

        // Move the modal card
        modalCard.style.transform = `translateY(${deltaY}px)`;
        modalCard.style.transition = 'none';

        // Fade overlay
        const maxDrag = window.innerHeight * 0.4;
        const progress = Math.min(1, deltaY / maxDrag);
        activeModal.style.background = `rgba(15, 23, 42, ${0.45 * (1 - progress * 0.5)})`;
    }

    function handleTouchEnd(e) {
        if (!activeModal || !modalCard || !isDragging) {
            isDragging = false;
            activeModal = null;
            modalCard = null;
            return;
        }

        isDragging = false;

        const deltaY = currentY - startY;
        const deltaTime = Date.now() - startTime;
        const velocity = deltaY / deltaTime;

        // Reset styles
        modalCard.style.transition = '';
        activeModal.style.background = '';

        // Close if swiped far enough or fast enough
        if (deltaY > SWIPE_THRESHOLD || velocity > SWIPE_VELOCITY_THRESHOLD) {
            closeModal(activeModal);
        } else {
            // Snap back
            modalCard.style.transform = '';
        }

        activeModal = null;
        modalCard = null;
    }

    function closeModal(modal) {
        if (!modal) return;

        // Animate out
        const card = modal.querySelector('.modal-card');
        if (card) {
            card.style.transform = 'translateY(100%)';
            card.style.transition = 'transform 0.2s ease-out';
        }

        setTimeout(function() {
            modal.classList.add('hidden');
            modal.classList.remove('flex');
            if (card) {
                card.style.transform = '';
                card.style.transition = '';
            }
            document.body.style.overflow = '';
        }, 200);
    }

    function openModal(modal) {
        if (!modal) return;

        document.body.style.overflow = 'hidden';
        modal.classList.remove('hidden');
        modal.classList.add('flex');

        // Animate in on mobile
        if (isMobile()) {
            const card = modal.querySelector('.modal-card');
            if (card) {
                card.style.transform = 'translateY(100%)';
                requestAnimationFrame(function() {
                    card.style.transition = 'transform 0.25s cubic-bezier(0.4, 0, 0.2, 1)';
                    card.style.transform = 'translateY(0)';
                });
            }
        }
    }

    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Re-init when htmx swaps content
    document.body.addEventListener('htmx:afterSwap', init);

    // Expose to global scope
    window.modalController = {
        open: openModal,
        close: closeModal
    };
})();
