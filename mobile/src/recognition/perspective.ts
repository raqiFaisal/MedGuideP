import { requireOptionalNativeModule } from 'expo';

export async function rectifyPackage(uri: string): Promise<string | null> {
  const native = requireOptionalNativeModule<{ rectify(imageUri: string): Promise<string | null> }>('MedGuideVision');
  return native ? native.rectify(uri) : null;
}
