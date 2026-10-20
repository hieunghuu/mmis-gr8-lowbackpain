import { marked } from 'marked'
import source from '../../docs/huong-dan-su-dung.md?raw'

const images = import.meta.glob('../../docs/images/*.png', { eager: true, query: '?url', import: 'default' }) as Record<
  string,
  string
>
const urlByName = Object.fromEntries(Object.entries(images).map(([path, url]) => [path.split('/').pop()!, url]))

const html = (marked.parse(source, { async: false }) as string).replace(
  /<img src="images\/([^"]+)"/g,
  (_, name: string) => `<img loading="lazy" src="${urlByName[name] ?? ''}"`,
)

export default function GuidePage() {
  return <article className="guide" dangerouslySetInnerHTML={{ __html: html }} />
}
