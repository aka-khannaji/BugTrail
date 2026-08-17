function computeTotal(cart) {
  const subtotal = cart.items[0].price * cart.items[0].quantity;
  let total = subtotal;
  for (let i = 1; i < cart.items.length; i++) {
    total += cart.items[i].price * cart.items[i].quantity;
  }
  return total;
}

module.exports = { computeTotal };
