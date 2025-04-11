// static/js/locations.js - Gestion dynamique des localisations
document.addEventListener('DOMContentLoaded', () => {
    // Constantes pour les sélecteurs DOM
    const TREE_CONTAINER = document.getElementById('location-tree');
    const SEARCH_INPUT = document.getElementById('location-search');
    const EDIT_FORM = document.getElementById('edit-location-form');

    // Vérification des éléments DOM
    if (!TREE_CONTAINER || !SEARCH_INPUT || !EDIT_FORM) {
        console.error('Éléments DOM manquants :', { TREE_CONTAINER, SEARCH_INPUT, EDIT_FORM });
        return;
    }

    // 1. Fonctionnalité de recherche avec débouncing
    let searchTimeout;
    SEARCH_INPUT.addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            const searchTerm = e.target.value.toLowerCase();
            const locations = TREE_CONTAINER.querySelectorAll('.location-node');

            locations.forEach(node => {
                const text = node.textContent.toLowerCase();
                node.style.display = text.includes(searchTerm) ? 'block' : 'none';
            });
        }, 300); // Délai de 300ms pour le débouncing
    });

    // 2. Gestion de l'arborescence (afficher/masquer les enfants, éditer, supprimer)
    TREE_CONTAINER.addEventListener('click', (e) => {
        const target = e.target;

        // Toggle des enfants
        if (target.classList.contains('toggle-children')) {
            const parentLi = target.closest('li');
            const childrenUl = parentLi.querySelector('ul');
            if (childrenUl) {
                childrenUl.hidden = !childrenUl.hidden;
                target.textContent = childrenUl.hidden ? '[+]' : '[-]';
                target.setAttribute('aria-expanded', !childrenUl.hidden);
            }
        }

        // Édition rapide
        if (target.classList.contains('edit-location')) {
            const locationId = target.dataset.locationId;
            if (locationId) {
                openEditModal(locationId);
            }
        }

        // Suppression
        if (target.classList.contains('delete-location')) {
            const locationId = target.dataset.locationId;
            if (locationId) {
                confirmDelete(locationId);
            }
        }
    });

    // 3. Fonction d'édition modale
    function openEditModal(locationId) {
        fetch(`/api/locations/${locationId}`, {
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            }
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`Erreur HTTP ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            EDIT_FORM.elements['code'].value = data.code || '';
            EDIT_FORM.elements['name'].value = data.name || '';
            EDIT_FORM.elements['type'].value = data.type || '';
            EDIT_FORM.elements['parent'].value = data.parent_id || '';
            EDIT_FORM.dataset.locationId = locationId;

            const modal = new bootstrap.Modal(document.getElementById('editLocationModal'));
            modal.show();
        })
        .catch(error => {
            console.error('Erreur lors de la récupération des données de localisation:', error);
            showAlert('Erreur lors de la récupération des données', 'danger');
        });
    }

    // 4. Soumission du formulaire d'édition
    EDIT_FORM.addEventListener('submit', (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        const locationId = e.target.dataset.locationId;

        fetch(`/api/locations/${locationId}`, {
            method: 'PUT',
            body: formData,
            headers: {
                'Accept': 'application/json'
            }
        })
        .then(response => {
            if (response.ok) {
                window.location.reload();
            } else {
                throw new Error(`Erreur HTTP ${response.status}`);
            }
        })
        .catch(error => {
            console.error('Erreur lors de la mise à jour de la localisation:', error);
            showAlert('Erreur lors de la mise à jour de la localisation', 'danger');
        });
    });

    // 5. Confirmation de suppression
    function confirmDelete(locationId) {
        const confirm = window.confirm('Confirmez-vous la suppression de cette localisation ?');
        if (confirm) {
            fetch(`/api/locations/${locationId}`, {
                method: 'DELETE',
                headers: {
                    'Accept': 'application/json'
                }
            })
            .then(response => {
                if (response.ok) {
                    window.location.reload();
                } else {
                    throw new Error(`Erreur HTTP ${response.status}`);
                }
            })
            .catch(error => {
                console.error('Erreur lors de la suppression de la localisation:', error);
                showAlert('Suppression impossible (peut contenir des sous-localisations)', 'danger');
            });
        }
    }

    // 6. Gestion des alertes
    function showAlert(message, type) {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.setAttribute('role', 'alert');
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Fermer l'alerte"></button>
        `;
        const mainElement = document.querySelector('main');
        if (mainElement) {
            mainElement.prepend(alertDiv);
        }
    }
});