
const API_BASE = "/api";

let cart = [];
let currentUser = null;
async function loadProducts() {
    const productList = document.getElementById("product-list");

    try {
        const response = await fetch(`${API_BASE}/products`);

        if (!response.ok) {
            throw new Error("Unable to retrieve products");
        }

        const products = await response.json();

        productList.innerHTML = "";

        products.forEach(product => {
            const card = document.createElement("div");
            card.className = "product-card";

            const name = document.createElement("h3");
            name.textContent = product.name;

            const description = document.createElement("p");
            description.textContent = product.description;

            const price = document.createElement("div");
            price.className = "product-price";
            price.textContent = `$${Number(product.price).toFixed(2)}`;

            const button = document.createElement("button");
            button.textContent = "Add to Cart";
            button.addEventListener("click", () => addToCart(product));

            card.append(name, description, price, button);
            productList.appendChild(card);
        });

    } catch (error) {
        console.error("Product loading error:", error);
        productList.textContent =
            "Unable to load products. Please try again later.";
    }
}


function addToCart(product) {
    cart.push(product);

    document.getElementById("cart-count").textContent = cart.length;

    renderCart();
}

function renderCart() {
    const cartItems = document.getElementById("cart-items");
    const cartTotal = document.getElementById("cart-total");

    cartItems.innerHTML = "";

    if (cart.length === 0) {
        cartItems.textContent = "Your cart is currently empty.";
        cartTotal.textContent = "Total: $0.00";
        return;
    }

    let total = 0;

    cart.forEach((product, index) => {
        total += Number(product.price);

        const item = document.createElement("div");
        item.className = "product-card";

        const name = document.createElement("h3");
        name.textContent = product.name;

        const price = document.createElement("p");
        price.textContent = `$${Number(product.price).toFixed(2)}`;

        const removeButton = document.createElement("button");
        removeButton.textContent = "Remove";
        removeButton.addEventListener("click", () => {
            cart.splice(index, 1);
            document.getElementById("cart-count").textContent = cart.length;
            renderCart();
        });

        item.append(name, price, removeButton);
        cartItems.appendChild(item);
    });

    cartTotal.textContent = `Total: $${total.toFixed(2)}`;
}

document.addEventListener("DOMContentLoaded", loadProducts);


// Display account messages
function showAccountMessage(message, success) {
    const output = document.getElementById("account-message");

    output.textContent = message;
    output.style.color = success ? "green" : "red";
}

// Customer registration
document.getElementById("register-form").addEventListener("submit", async (event) => {
    event.preventDefault();

    const userData = {
        username: document.getElementById("register-username").value,
        email: document.getElementById("register-email").value,
        password: document.getElementById("register-password").value
    };

    try {
        const response = await fetch("/api/users/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(userData)
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || "Registration failed");
        }

        showAccountMessage("Account registration request successful!", true);
        event.target.reset();

    } catch (error) {
        showAccountMessage(error.message, false);
    }
});

// Customer login
document.getElementById("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();

    const loginData = {
        email: document.getElementById("login-email").value,
        password: document.getElementById("login-password").value
    };

    try {
        const response = await fetch("/api/users/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(loginData)
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || "Login failed");
        }
        currentUser = result;
        showAccountMessage(`Welcome, ${result.username}!`, true);
        event.target.reset();

    } catch (error) {
        showAccountMessage(error.message, false);
    }
});

document.getElementById("checkout-button").addEventListener("click", async () => {
    const message = document.getElementById("checkout-message");

    if (!currentUser) {
        message.textContent = "Please log in before placing an order.";
        return;
    }

    if (cart.length === 0) {
        message.textContent = "Your cart is empty.";
        return;
    }

    const quantities = {};

    cart.forEach(product => {
        quantities[product.id] = (quantities[product.id] || 0) + 1;
    });

    const orderData = {
        user_id: currentUser.user_id,
        items: Object.entries(quantities).map(([id, quantity]) => ({
            product_id: Number(id),
            quantity: quantity
        }))
    };

    try {
        const response = await fetch("/api/orders/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(orderData)
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || "Order failed");
        }

        message.textContent = `Order placed! Order ID: ${result.order_id}`;

        cart = [];
        document.getElementById("cart-count").textContent = "0";
        renderCart();

    } catch (error) {
        message.textContent = error.message;
    }
});
