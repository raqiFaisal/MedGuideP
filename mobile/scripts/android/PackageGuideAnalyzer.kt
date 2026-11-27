package expo.modules.camera.analyzers

import android.os.SystemClock
import android.util.Base64
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import kotlin.math.roundToInt

/** Samples low-resolution luminance from preview frames without capturing or saving photos. */
internal class PackageGuideAnalyzer(
  private val emit: (Map<String, Any>) -> Unit
) : ImageAnalysis.Analyzer {
  private var lastFrame = Long.MIN_VALUE

  override fun analyze(image: ImageProxy) {
    try {
      val now = SystemClock.elapsedRealtime()
      if (lastFrame != Long.MIN_VALUE && now - lastFrame < 1100) return
      lastFrame = now
      val crop = image.cropRect
      if (crop.width() < 2 || crop.height() < 2) return
      val scale = minOf(1.0, 256.0 / maxOf(crop.width(), crop.height()))
      val width = (crop.width() * scale).roundToInt().coerceAtLeast(2)
      val height = (crop.height() * scale).roundToInt().coerceAtLeast(2)
      val rotation = image.imageInfo.rotationDegrees
      val rotated = rotation == 90 || rotation == 270
      val outputWidth = if (rotated) height else width
      val outputHeight = if (rotated) width else height
      val data = ByteArray(outputWidth * outputHeight)
      val plane = image.planes.first()
      val offset = plane.buffer.position()
      for (y in 0 until height) {
        val sourceY = crop.top + y * crop.height() / height
        for (x in 0 until width) {
          val sourceX = crop.left + x * crop.width() / width
          val index = offset + sourceY * plane.rowStride + sourceX * plane.pixelStride
          if (index >= plane.buffer.limit()) return
          val target = when (rotation) {
            90 -> x * height + (height - 1 - y)
            180 -> (height - 1 - y) * width + (width - 1 - x)
            270 -> (width - 1 - x) * height + y
            else -> y * width + x
          }
          data[target] = plane.buffer.get(index)
        }
      }
      emit(mapOf("luma" to Base64.encodeToString(data, Base64.NO_WRAP), "width" to outputWidth, "height" to outputHeight))
    } finally {
      image.close()
    }
  }
}
