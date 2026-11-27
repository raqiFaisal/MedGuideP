export function logicalArabic(visual: string) {
  const rightToLeft = Array.from(visual).reverse().join('');
  return rightToLeft.replace(/[0-9٠-٩۰-۹A-Za-z]+(?:[./٫٬-][0-9٠-٩۰-۹A-Za-z]+)*/g,
    run => Array.from(run).reverse().join(''));
}
