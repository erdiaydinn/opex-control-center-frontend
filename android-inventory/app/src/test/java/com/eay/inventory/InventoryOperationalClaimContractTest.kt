package com.eay.inventory

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class InventoryOperationalClaimContractTest {
    @Test
    fun `claim hash matches backend canonical vector`() {
        assertEquals(
            "4dcba75ca8d3ab0e9fde4a33ea20454c7f1370bc2b87893f5deb153525455a1d",
            InventoryOperationalClaimContract.hash(
                "11111111-1111-4111-8111-111111111111",
                "SHIFT-A",
            ),
        )
    }

    @Test
    fun `claim proof is bound to mission and active shift`() {
        val base = InventoryOperationalClaimContract.hash(
            "11111111-1111-4111-8111-111111111111",
            "SHIFT-A",
        )
        assertNotEquals(
            base,
            InventoryOperationalClaimContract.hash(
                "22222222-2222-4222-8222-222222222222",
                "SHIFT-A",
            ),
        )
        assertNotEquals(
            base,
            InventoryOperationalClaimContract.hash(
                "11111111-1111-4111-8111-111111111111",
                "SHIFT-B",
            ),
        )
    }

    @Test
    fun `invalid shift provenance fails closed before signing`() {
        assertThrows(IllegalArgumentException::class.java) {
            InventoryOperationalClaimContract.hash(
                "11111111-1111-4111-8111-111111111111",
                "SHIFT A",
            )
        }
    }
}
