package com.eay.mobile.fieldui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

private val Brand = Color(0xFFDF1067)
private val BrandDark = Color(0xFFFF78AA)
private val Ink = Color(0xFF24151B)
private val NightInk = Color(0xFFFFF7FA)

private val FieldTypography = Typography(
    displaySmall = TextStyle(fontSize = 32.sp, lineHeight = 38.sp, fontWeight = FontWeight.Bold),
    headlineMedium = TextStyle(fontSize = 24.sp, lineHeight = 30.sp, fontWeight = FontWeight.Bold),
    titleLarge = TextStyle(fontSize = 20.sp, lineHeight = 26.sp, fontWeight = FontWeight.SemiBold),
    bodyLarge = TextStyle(fontSize = 17.sp, lineHeight = 25.sp, fontWeight = FontWeight.Normal),
    labelLarge = TextStyle(fontSize = 14.sp, lineHeight = 20.sp, fontWeight = FontWeight.SemiBold),
)

private val FieldShapes = Shapes(
    small = RoundedCornerShape(12.dp),
    medium = RoundedCornerShape(20.dp),
    large = RoundedCornerShape(28.dp),
)

private val FieldLightColors = lightColorScheme(
    primary = Brand,
    onPrimary = Color.White,
    primaryContainer = Color(0xFFFFD9E7),
    onPrimaryContainer = Color(0xFF3E001D),
    secondary = Color(0xFF6D4C5A),
    onSecondary = Color.White,
    secondaryContainer = Color(0xFFF6DDE7),
    onSecondaryContainer = Color(0xFF29151D),
    error = Color(0xFFBA1A1A),
    errorContainer = Color(0xFFFFDAD6),
    background = Color(0xFFFFF8FA),
    onBackground = Ink,
    surface = Color(0xFFFFF8FA),
    onSurface = Ink,
    surfaceVariant = Color(0xFFF4E9EE),
    onSurfaceVariant = Color(0xFF534249),
    outline = Color(0xFF857078),
    outlineVariant = Color(0xFFD8C2CA),
)

private val FieldDarkColors = darkColorScheme(
    primary = BrandDark,
    onPrimary = Color(0xFF65002F),
    primaryContainer = Color(0xFF8E0046),
    onPrimaryContainer = Color(0xFFFFD9E7),
    secondary = Color(0xFFD9BDC8),
    onSecondary = Color(0xFF3C2B32),
    secondaryContainer = Color(0xFF544149),
    onSecondaryContainer = Color(0xFFF6DDE7),
    error = Color(0xFFFFB4AB),
    errorContainer = Color(0xFF93000A),
    background = Color(0xFF1A1115),
    onBackground = NightInk,
    surface = Color(0xFF1A1115),
    onSurface = NightInk,
    surfaceVariant = Color(0xFF534249),
    onSurfaceVariant = Color(0xFFD8C2CA),
    outline = Color(0xFFA18A93),
    outlineVariant = Color(0xFF534249),
)

@Composable
fun EayFieldTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = if (darkTheme) FieldDarkColors else FieldLightColors,
        typography = FieldTypography,
        shapes = FieldShapes,
        content = content,
    )
}
