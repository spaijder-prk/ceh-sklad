package ru.ceh.sklad.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class SaleCartTest {
    private val product = StockItem(
        location_id = "rep-1",
        location_name = "Иван",
        product_id = "p-1",
        sku = "A-1",
        product_name = "Товар",
        unit_name = "шт",
        quantity = 5.0,
        retail_price = 100.0,
        wholesale_price = 80.0,
    )

    @Test
    fun sameProductIsMergedAndTotalUsesSelectedPriceType() {
        val first = addToSaleCart(emptyList(), product, 1.0)
        val cart = addToSaleCart(first, product, 2.0)

        assertEquals(1, cart.size)
        assertEquals(3.0, cart.single().quantity, 0.0001)
        assertEquals(300.0, saleCartTotal(cart, "retail"), 0.0001)
        assertEquals(240.0, saleCartTotal(cart, "wholesale"), 0.0001)
    }

    @Test
    fun cartCannotExceedLastConfirmedStock() {
        val cart = addToSaleCart(emptyList(), product, 4.0)
        assertThrows(IllegalArgumentException::class.java) {
            addToSaleCart(cart, product, 2.0)
        }
    }
}
