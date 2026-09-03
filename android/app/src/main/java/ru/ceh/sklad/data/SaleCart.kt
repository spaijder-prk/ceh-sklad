package ru.ceh.sklad.data

data class SaleCartLine(
    val product: StockItem,
    val quantity: Double,
)

fun addToSaleCart(cart: List<SaleCartLine>, product: StockItem, quantity: Double): List<SaleCartLine> {
    require(quantity > 0) { "Количество должно быть больше нуля" }
    val existing = cart.firstOrNull { it.product.product_id == product.product_id }
    val newQuantity = (existing?.quantity ?: 0.0) + quantity
    require(newQuantity <= product.quantity + 0.000001) {
        "Количество в корзине превышает последний подтвержденный остаток"
    }
    return if (existing == null) {
        cart + SaleCartLine(product, quantity)
    } else {
        cart.map { if (it.product.product_id == product.product_id) it.copy(quantity = newQuantity) else it }
    }
}

fun saleUnitPrice(product: StockItem, priceType: String): Double =
    if (priceType == "wholesale") product.wholesale_price else product.retail_price

fun saleCartTotal(cart: List<SaleCartLine>, priceType: String): Double =
    cart.sumOf { it.quantity * saleUnitPrice(it.product, priceType) }
