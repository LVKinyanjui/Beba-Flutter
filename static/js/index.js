const host = "http://localhost:5000"
const socket = io(host);
let token = localStorage.getItem('token');
let isDriver = localStorage.getItem('is_driver') === 'true';

document.addEventListener('DOMContentLoaded', () => {
    if (token) {
        updateNavForLoggedIn();
        loadVehicles();
        loadListings('rentals');
        loadListings('shamba');
        loadListings('apartments');
        loadTransportJobs();
    }
    showSection('home');
});

function updateNavForLoggedIn() {
    document.getElementById('auth-nav').innerHTML = `
        <span class="navbar-text me-2">Welcome, ${localStorage.getItem('email')}</span>
        <button class="btn btn-outline-danger" onclick="logout()">Logout</button>
    `;
}

function showSection(sectionId) {
    document.querySelectorAll('main section').forEach(section => section.style.display = 'none');
    document.getElementById(`${sectionId}-section`).style.display = 'block';
}

function showLogin() {
    document.getElementById('login-form').style.display = 'block';
    document.getElementById('signup-form').style.display = 'none';
}

function showSignup() {
    document.getElementById('signup-form').style.display = 'block';
    document.getElementById('login-form').style.display = 'none';
}

async function login(event) {
    event.preventDefault();
    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;
    try {
        const response = await axios.post(`${host}/login`, { email, password });
        token = response.data.access_token;
        isDriver = response.data.is_driver;
        localStorage.setItem('token', token);
        localStorage.setItem('is_driver', isDriver);
        localStorage.setItem('email', email);
        updateNavForLoggedIn();
        loadData();
        showSection('vehicles');
    } catch (error) {
        alert('Login failed: ' + (error.response?.data?.error || 'Unknown error'));
    }
}

async function signup(event) {
    event.preventDefault();
    const data = {
        full_name: document.getElementById('signup-fullname').value,
        phone: document.getElementById('signup-phone').value,
        id_number: document.getElementById('signup-id').value,
        kra_pin: document.getElementById('signup-kra').value,
        email: document.getElementById('signup-email').value,
        password: document.getElementById('signup-password').value,
        is_driver: document.getElementById('signup-is-driver').checked
    };
    try {
        await axios.post(`${host}/signup`, data);
        alert('Signup successful! Please login.');
        showLogin();
    } catch (error) {
        alert('Signup failed: ' + (error.response?.data?.error || 'Unknown error'));
    }
}

function logout() {
    localStorage.clear();
    token = null;
    isDriver = false;
    document.getElementById('auth-nav').innerHTML = `
        <button class="btn btn-primary me-2" onclick="showLogin()">Login</button>
        <button class="btn btn-outline-primary" onclick="showSignup()">Sign Up</button>
    `;
    showSection('home');
}

function showAddVehicleForm() {
    if (!token) return alert('Please login first');
    document.getElementById('add-vehicle-form').style.display = 'block';
}

async function addVehicle(event) {
    event.preventDefault();
    const formData = new FormData();
    formData.append('vehicle_reg', document.getElementById('vehicle-reg').value);
    formData.append('vehicle_type', document.getElementById('vehicle-type').value);
    const tons = document.getElementById('vehicle-tons').value;
    if (tons) formData.append('tons', tons);
    const image = document.getElementById('vehicle-image').files[0];
    if (image) formData.append('image', image);
    
    try {
        const response = await axios.post(`${host}/vehicles`, formData, {
            headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'multipart/form-data' }
        });
        alert('Vehicle added successfully (free)');
        document.getElementById('add-vehicle-form').style.display = 'none';
        loadVehicles();
    } catch (error) {
        alert('Failed to add vehicle: ' + (error.response?.data?.error || 'Unknown error'));
    }
}

async function loadVehicles() {
    if (!token) return;
    try {
        const myVehicles = await axios.get(`${host}/vehicles`, { headers: { 'Authorization': `Bearer ${token}` } });
        document.getElementById('my-vehicles').innerHTML = myVehicles.data.map(v => `
            <div class="col-md-4 vehicle-card">
                <div class="card">
                    <img src="${v.image || 'https://via.placeholder.com/150'}" class="card-img-top" alt="${v.vehicle_reg}">
                    <div class="card-body">
                        <h5 class="card-title">${v.vehicle_type} - ${v.vehicle_reg}</h5>
                        <p class="card-text">Tons: ${v.tons || 'N/A'}</p>
                    </div>
                </div>
            </div>
        `).join('');

        const availableVehicles = await axios.get(`${host}/listings/vehicles`, { headers: { 'Authorization': `Bearer ${token}` } });
        document.getElementById('available-vehicles').innerHTML = availableVehicles.data.map(v => `
            <div class="col-md-4 vehicle-card">
                <div class="card">
                    <img src="${v.image || 'https://via.placeholder.com/150'}" class="card-img-top" alt="${v.vehicle_reg}">
                    <div class="card-body">
                        <h5 class="card-title">${v.vehicle_type} - ${v.vehicle_reg}</h5>
                        <p class="card-text">Tons: ${v.tons || 'N/A'}</p>
                        <button class="btn btn-primary" onclick="bookVehicle(${v.id})">Book (Ksh 100)</button>
                    </div>
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Error loading vehicles:', error);
    }
}

async function bookVehicle(vehicleId) {
    const pickup = prompt('Enter pickup location:');
    const destination = prompt('Enter destination:');
    const budget = prompt('Enter your budget:');
    if (!pickup || !destination || !budget) return alert('All fields are required');
    
    try {
        const response = await axios.post(`${host}/book_vehicle/${vehicleId}`, {
            pickup,
            destination,
            budget: parseInt(budget)
        }, {
            headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
        });
        if (response.status === 202) {
            const checkoutId = response.data.checkout_id;
            alert(`Payment initiated. Please complete Ksh 100 payment on your phone using M-Pesa. Checkout ID: ${checkoutId}`);
            // Optionally, poll for payment status or rely on socket
            console.log(`Awaiting M-Pesa confirmation for Checkout ID: ${checkoutId}`);
        } else {
            throw new Error('Unexpected response status');
        }
    } catch (error) {
        alert('Booking failed: ' + (error.response?.data?.error || 'Unknown error'));
    }
}

function showAddTransportJobForm() {
    if (!token) return alert('Please login first');
    document.getElementById('add-transport-job-form').style.display = 'block';
}

async function addTransportJob(event) {
    event.preventDefault();
    const data = {
        pickup_location: document.getElementById('job-pickup').value,
        destination: document.getElementById('job-destination').value,
        description: document.getElementById('job-description').value,
        budget: parseInt(document.getElementById('job-budget').value)
    };
    try {
        const response = await axios.post(`${host}/transport_jobs`, data, {
            headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
        });
        if (response.status === 202) {
            const checkoutId = response.data.checkout_id;
            alert(`Payment initiated. Please complete Ksh 100 payment on your phone using M-Pesa. Checkout ID: ${checkoutId}`);
            document.getElementById('add-transport-job-form').style.display = 'none';
        } else {
            throw new Error('Unexpected response status');
        }
    } catch (error) {
        alert('Failed to post job: ' + (error.response?.data?.error || 'Unknown error'));
    }
}

async function searchTransportJobs(event) {
    event.preventDefault();
    const pickup = document.getElementById('search-pickup').value;
    const destination = document.getElementById('search-destination').value;
    try {
        const response = await axios.get(`${host}/transport_jobs?pickup_location=${pickup}&destination=${destination}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        document.getElementById('transport-jobs').innerHTML = response.data.map(j => `
            <div class="col-md-4 job-card">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title">${j.pickup_location} to ${j.destination}</h5>
                        <p class="card-text">Description: ${j.description}</p>
                        <p class="card-text">Budget: Ksh ${j.budget}</p>
                        <p class="card-text">Posted: ${new Date(j.timestamp).toLocaleString()}</p>
                    </div>
                </div>
            </div>
        `).join('');
    } catch (error) {
        alert('Search failed: ' + (error.response?.data?.error || 'Unknown error'));
    }
}

function loadTransportJobs() {
    searchTransportJobs({ preventDefault: () => {} }); // Load all jobs initially
}

function showAddListingForm(type) {
    if (!token) return alert('Please login first');
    document.getElementById('listing-form-title').textContent = `Add ${type.charAt(0).toUpperCase() + type.slice(1)} Listing`;
    document.getElementById('listing-type').value = type;
    document.getElementById('shamba-title-deed').style.display = type === 'shamba' ? 'block' : 'none';
    document.getElementById('add-listing-form').style.display = 'block';
}

async function addListing(event) {
    event.preventDefault();
    const type = document.getElementById('listing-type').value;
    const formData = new FormData();
    formData.append('location', document.getElementById('listing-location').value);
    formData.append('details', document.getElementById('listing-details').value);
    formData.append('price', document.getElementById('listing-price').value);
    const images = document.getElementById('listing-images').files;
    for (let i = 0; i < images.length; i++) formData.append('images', images[i]);
    if (type === 'shamba') {
        const titleDeed = document.getElementById('listing-title-deed').files[0];
        if (titleDeed) formData.append('title_deed', titleDeed);
    }
    
    try {
        const response = await axios.post(`${host}/listings/${type}`, formData, {
            headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'multipart/form-data' }
        });
        if (response.status === 202) {
            const checkoutId = response.data.checkout_id;
            alert(`Payment initiated. Please complete Ksh 100 payment on your phone using M-Pesa. Checkout ID: ${checkoutId}`);
            document.getElementById('add-listing-form').style.display = 'none';
        } else {
            throw new Error('Unexpected response status');
        }
    } catch (error) {
        alert('Failed to add listing: ' + (error.response?.data?.error || 'Unknown error'));
    }
}

async function loadListings(type) {
    if (!token) return;
    try {
        const response = await axios.get(`${host}/listings/${type}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        document.getElementById('my-listings').innerHTML = response.data.map(l => `
            <div class="col-md-4 listing-card">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title">${l.details}</h5>
                        <p class="card-text">Location: ${l.location}</p>
                        <p class="card-text">Price: Ksh ${l.price}</p>
                    </div>
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error(`Error loading ${type}:`, error);
    }
}

function showAddInsuranceForm() {
    if (!token) return alert('Please login first');
    document.getElementById('add-insurance-form').style.display = 'block';
}

async function addInsurance(event) {
    event.preventDefault();
    const data = {
        vehicle_id: parseInt(document.getElementById('insurance-vehicle-id').value),
        policy_number: document.getElementById('insurance-policy').value,
        expiry_date: document.getElementById('insurance-expiry').value
    };
    try {
        const response = await axios.post(`${host}/insurance`, data, {
            headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
        });
        alert('Insurance added successfully (free)');
        document.getElementById('add-insurance-form').style.display = 'none';
    } catch (error) {
        alert('Failed to add insurance: ' + (error.response?.data?.error || 'Unknown error'));
    }
}

function loadData() {
    loadVehicles();
    loadListings('rentals');
    loadListings('shamba');
    loadListings('apartments');
    loadTransportJobs();
}

// Socket.IO listeners for real-time updates
socket.on('vehicle_added', () => {
    console.log('New vehicle added');
    loadVehicles();
});
socket.on('rentals_added', () => {
    console.log('New rental listing added');
    loadListings('rentals');
});
socket.on('shamba_added', () => {
    console.log('New shamba listing added');
    loadListings('shamba');
});
socket.on('apartments_added', () => {
    console.log('New apartment listing added');
    loadListings('apartments');
});
socket.on('transport_job_added', () => {
    console.log('New transport job added');
    loadTransportJobs();
});
socket.on('payment_confirmed', (data) => {
    console.log(`Payment confirmed for ${data.type} ID: ${data.booking_id || data.listing_id || data.job_id}`);
    loadData(); // Refresh all data after payment confirmation
});
socket.on('connect', () => console.log('Connected to WebSocket'));
socket.on('disconnect', () => console.log('Disconnected from WebSocket'));


