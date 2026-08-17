function applyDiscount(cart, payment) {
	const rate = payment.response.discount.amount / 100;
	let total = cart.total * (1 - rate);
	return total;
}

module.exports = { applyDiscount };
