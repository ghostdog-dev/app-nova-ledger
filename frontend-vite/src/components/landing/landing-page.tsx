import { TextureOverlay } from './texture-overlay';
import { Navbar } from './navbar';
import { Hero } from './hero';
import { SocialProof } from './social-proof';
import { Pain } from './pain';
import { HowItWorks } from './how-it-works';
import { Benefits } from './benefits';
import { Preview } from './preview';
import { Pricing } from './pricing';
import { Footer } from './footer';

export function LandingPage() {
  return (
    <div style={{ overflowX: 'hidden', maxWidth: '100vw' }}>
      <TextureOverlay />
      <Navbar />
      <Hero />
      <SocialProof />
      <Pain />
      <HowItWorks />
      <Benefits />
      <Preview />
      <Pricing />
      <Footer />
    </div>
  );
}
