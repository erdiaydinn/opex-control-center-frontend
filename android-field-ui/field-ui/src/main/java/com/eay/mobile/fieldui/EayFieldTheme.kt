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
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

private val EayNavy = Color(0xFF07235B)
private val EayMagenta = Color(0xFFD20A6D)
private val EayElectricBlue = Color(0xFF1F6BFF)
private val EayCharcoal = Color(0xFF111827)
private val EaySurface = Color(0xFFF8FAFC)
private val EayBorder = Color(0xFFE5E7EB)
private val EayBody = Color(0xFF374151)

private val FieldTypography = Typography(
    displaySmall = TextStyle(fontFamily = FontFamily.SansSerif, fontSize = 32.sp, lineHeight = 38.sp, fontWeight = FontWeight.ExtraBold),
    headlineMedium = TextStyle(fontFamily = FontFamily.SansSerif, fontSize = 24.sp, lineHeight = 30.sp, fontWeight = FontWeight.Bold),
    titleLarge = TextStyle(fontFamily = FontFamily.SansSerif, fontSize = 20.sp, lineHeight = 26.sp, fontWeight = FontWeight.SemiBold),
    bodyLarge = TextStyle(fontFamily = FontFamily.SansSerif, fontSize = 17.sp, lineHeight = 25.sp, fontWeight = FontWeight.Normal),
    labelLarge = TextStyle(fontFamily = FontFamily.SansSerif, fontSize = 14.sp, lineHeight = 20.sp, fontWeight = FontWeight.SemiBold),
)

private val FieldShapes = Shapes(
    small = RoundedCornerShape(12.dp),
    medium = RoundedCornerShape(16.dp),
    large = RoundedCornerShape(20.dp),
)

private val FieldLightColors = lightColorScheme(
    primary = EayNavy,
    onPrimary = Color.White,
    primaryContainer = Color(0xFFDCE7FF),
    onPrimaryContainer = EayNavy,
    secondary = EayElectricBlue,
    onSecondary = Color.White,
    secondaryContainer = Color(0xFFDDE7FF),
    onSecondaryContainer = Color(0xFF071F51),
    tertiary = EayMagenta,
    onTertiary = Color.White,
    tertiaryContainer = Color(0xFFFFD8E8),
    onTertiaryContainer = Color(0xFF4A0024),
    error = Color(0xFFBA1A1A),
    errorContainer = Color(0xFFFFDAD6),
    background = EaySurface,
    onBackground = EayCharcoal,
    surface = Color.White,
    onSurface = EayCharcoal,
    surfaceVariant = Color(0xFFEEF2F7),
    onSurfaceVariant = EayBody,
    outline = Color(0xFF7A8495),
    outlineVariant = EayBorder,
)

private val FieldDarkColors = darkColorScheme(
    primary = Color(0xFFAEC7FF),
    onPrimary = Color(0xFF001A43),
    primaryContainer = EayNavy,
    onPrimaryContainer = Color(0xFFDCE7FF),
    secondary = Color(0xFF9DB9FF),
    onSecondary = Color(0xFF002D6E),
    secondaryContainer = Color(0xFF0A387F),
    onSecondaryContainer = Color(0xFFDDE7FF),
    tertiary = Color(0xFFFFA9CD),
    onTertiary = Color(0xFF650033),
    tertiaryContainer = Color(0xFF8C0049),
    onTertiaryContainer = Color(0xFFFFD8E8),
    error = Color(0xFFFFB4AB),
    errorContainer = Color(0xFF93000A),
    background = Color(0xFF07152E),
    onBackground = Color(0xFFF8FAFC),
    surface = Color(0xFF0B1C38),
    onSurface = Color(0xFFF8FAFC),
    surfaceVariant = Color(0xFF152A4A),
    onSurfaceVariant = Color(0xFFD2D9E6),
    outline = Color(0xFF94A1B5),
    outlineVariant = Color(0xFF31425F),
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
