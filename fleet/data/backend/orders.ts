// Order creation for ticketed events (demo copy, not production code)
export async function createOrder(userId: string, eventId: string, qty: number) {
  if (qty < 1 || qty > 10) throw new Error("Quantity must be 1-10");
  const intent = await stripe.paymentIntents.create({ amount: qty * 1500, currency: "usd" });
  return db.order.create({ data: { userId, eventId, qty, intentId: intent.id } });
}
