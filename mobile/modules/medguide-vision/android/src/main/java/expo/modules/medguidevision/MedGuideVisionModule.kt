package expo.modules.medguidevision

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import org.opencv.android.OpenCVLoader
import org.opencv.android.Utils
import org.opencv.core.Mat
import org.opencv.core.MatOfPoint
import org.opencv.core.MatOfPoint2f
import org.opencv.core.Point
import org.opencv.core.Size
import org.opencv.imgproc.Imgproc
import java.io.File
import kotlin.math.abs
import kotlin.math.hypot
import kotlin.math.roundToInt

class MedGuideVisionModule : Module() {
  override fun definition() = ModuleDefinition {
    Name("MedGuideVision")
    AsyncFunction("rectify") { uri: String ->
      val context = requireNotNull(appContext.reactContext)
      val source = Uri.parse(uri)
      val file = File(requireNotNull(source.path)).canonicalFile
      val cache = context.cacheDir.canonicalFile
      require(source.scheme == "file" && generateSequence(file.parentFile) { it.parentFile }.any { it == cache }) {
        "Perspective source must be an app cache file"
      }
      val bitmap = requireNotNull(BitmapFactory.decodeFile(file.path, BitmapFactory.Options().apply {
        inPreferredConfig = Bitmap.Config.ARGB_8888
      }))
      try {
        val corrected = Perspective.correct(bitmap) ?: return@AsyncFunction null
        try {
          val output = File.createTempFile("medguide-rectified-", ".jpg", cache)
          var saved = false
          try {
            saved = output.outputStream().use { corrected.compress(Bitmap.CompressFormat.JPEG, 95, it) }
            if (saved) Uri.fromFile(output).toString() else null
          } finally {
            if (!saved) output.delete()
          }
        } finally {
          corrected.recycle()
        }
      } finally {
        bitmap.recycle()
      }
    }
  }
}

private object Perspective {
  fun correct(bitmap: Bitmap): Bitmap? {
    if (minOf(bitmap.width, bitmap.height) < 64 || !OpenCVLoader.initLocal()) return null
    val original = Mat()
    val edges = Mat()
    val hierarchy = Mat()
    val kernel = Imgproc.getStructuringElement(Imgproc.MORPH_RECT, Size(3.0, 3.0))
    val contours = mutableListOf<MatOfPoint>()
    try {
      Utils.bitmapToMat(bitmap, original)
      Imgproc.cvtColor(original, edges, Imgproc.COLOR_RGBA2GRAY)
      Imgproc.GaussianBlur(edges, edges, Size(5.0, 5.0), 0.0)
      Imgproc.Canny(edges, edges, 50.0, 150.0)
      Imgproc.morphologyEx(edges, edges, Imgproc.MORPH_CLOSE, kernel)
      Imgproc.findContours(edges, contours, hierarchy, Imgproc.RETR_EXTERNAL, Imgproc.CHAIN_APPROX_SIMPLE)
      val candidates = contours.mapNotNull { corners(it, bitmap.width, bitmap.height) }
      return candidates.singleOrNull()?.let { warp(original, it) }
    } finally {
      contours.forEach { it.release() }
      original.release()
      edges.release()
      hierarchy.release()
      kernel.release()
    }
  }

  private fun corners(contour: MatOfPoint, width: Int, height: Int): List<Point>? {
    val area = Imgproc.contourArea(contour) / (width.toDouble() * height)
    if (area !in 0.48..0.92) return null
    val curve = MatOfPoint2f(*contour.toArray())
    val quad = MatOfPoint2f()
    try {
      Imgproc.approxPolyDP(curve, quad, .02 * Imgproc.arcLength(curve, true), true)
      if (quad.total() != 4L) return null
      val points = quad.toList()
      val polygon = MatOfPoint(*points.toTypedArray())
      val convex = try { Imgproc.isContourConvex(polygon) } finally { polygon.release() }
      if (!convex || points.any { it.x <= 1 || it.y <= 1 || it.x >= width - 2 || it.y >= height - 2 }) return null
      val ordered = listOf(points.minBy { it.x + it.y }, points.maxBy { it.x - it.y },
        points.maxBy { it.x + it.y }, points.minBy { it.x - it.y })
      if (ordered.distinct().size != 4) return null
      for (i in ordered.indices) {
        val a = ordered[(i + 3) % 4]
        val b = ordered[i]
        val c = ordered[(i + 1) % 4]
        val ab = length(a, b)
        val bc = length(b, c)
        val dot = (a.x - b.x) * (c.x - b.x) + (a.y - b.y) * (c.y - b.y)
        if (minOf(ab, bc) < 24 || abs(dot) / (ab * bc) > .56) return null
      }
      return ordered
    } finally {
      curve.release()
      quad.release()
    }
  }

  private fun length(a: Point, b: Point) = hypot(a.x - b.x, a.y - b.y)

  private fun warp(original: Mat, points: List<Point>): Bitmap {
    val width = maxOf(length(points[0], points[1]), length(points[2], points[3])).roundToInt()
    val height = maxOf(length(points[1], points[2]), length(points[3], points[0])).roundToInt()
    val source = MatOfPoint2f(*points.toTypedArray())
    val target = MatOfPoint2f(Point(0.0, 0.0), Point(width - 1.0, 0.0),
      Point(width - 1.0, height - 1.0), Point(0.0, height - 1.0))
    val transform = Imgproc.getPerspectiveTransform(source, target)
    val corrected = Mat()
    try {
      Imgproc.warpPerspective(original, corrected, transform, Size(width.toDouble(), height.toDouble()))
      return Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888).also { Utils.matToBitmap(corrected, it) }
    } finally {
      source.release()
      target.release()
      transform.release()
      corrected.release()
    }
  }
}
