import { produceArtifactSet } from './scripts/package-artifacts.mjs';
import { installConsumer } from './scripts/local-package-install.mjs';

const artifactSet = produceArtifactSet({
  repoRoot: process.cwd(), outDir: '/opt/pi-artifacts', build: false, source: null,
});
installConsumer({
  artifactSet, directory: '/opt/pi-install',
  packageNames: ['@earendil-works/pi-coding-agent'],
});
