import { useEffect, useRef } from 'react';
import fragment from './shaders/waves.frag?raw';
import { AnimationClock, BACKGROUND_FPS, drawingSize, FrameLimiter, shouldAnimate } from './animation';

export function Waves({ paused = false }: { paused?: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const pausedRef = useRef(paused);
  const updateRef = useRef<() => void>(() => {});
  useEffect(() => { pausedRef.current = paused; updateRef.current(); }, [paused]);
  useEffect(() => {
    const canvas = ref.current!;
    const gl = canvas.getContext('webgl', { alpha: false, antialias: false, depth: false, stencil: false, powerPreference: 'low-power' });
    if (!gl) { canvas.dataset.status = 'unavailable'; return; }
    let frame = 0, frames = 0, inView = false, dirty = true;
    let program: WebGLProgram | null = null;
    let buffer: WebGLBuffer | null = null;
    const shaders: WebGLShader[] = [];
    let scene: WebGLUniformLocation | null = null;
    const reduced = matchMedia('(prefers-reduced-motion: reduce)');
    const clock = new AnimationClock(), limiter = new FrameLimiter();
    canvas.dataset.fpsLimit = String(BACKGROUND_FPS);
    const halt = () => { cancelAnimationFrame(frame); frame = 0; clock.pause(); limiter.reset(); };
    function cleanupGL() {
      shaders.splice(0).forEach(shader => gl!.deleteShader(shader));
      gl!.deleteProgram(program); gl!.deleteBuffer(buffer);
      program = null; buffer = null;
    }
    function setup() {
      try {
        const compile = (type: number, source: string) => {
          const shader = gl!.createShader(type)!;
          shaders.push(shader); gl!.shaderSource(shader, source); gl!.compileShader(shader);
          if (!gl!.getShaderParameter(shader, gl!.COMPILE_STATUS)) throw new Error(gl!.getShaderInfoLog(shader) || 'Shader compilation failed');
          return shader;
        };
        program = gl!.createProgram()!;
        gl!.attachShader(program, compile(gl!.VERTEX_SHADER, 'attribute vec2 a_position; void main(){gl_Position=vec4(a_position,0.0,1.0);}'));
        gl!.attachShader(program, compile(gl!.FRAGMENT_SHADER, fragment));
        gl!.linkProgram(program);
        if (!gl!.getProgramParameter(program, gl!.LINK_STATUS)) throw new Error(gl!.getProgramInfoLog(program) || 'Shader linking failed');
        gl!.useProgram(program);
        buffer = gl!.createBuffer(); gl!.bindBuffer(gl!.ARRAY_BUFFER, buffer);
        gl!.bufferData(gl!.ARRAY_BUFFER, new Float32Array([-1,-1,3,-1,-1,3]), gl!.STATIC_DRAW);
        const position = gl!.getAttribLocation(program, 'a_position');
        gl!.enableVertexAttribArray(position); gl!.vertexAttribPointer(position, 2, gl!.FLOAT, false, 0, 0);
        gl!.uniform3fv(gl!.getUniformLocation(program, 'u_colors[0]'), new Float32Array([.102,.078,.137,.718,.365,.412,.918,.804,.761,1,.961,.922,1,.961,.922,1,.961,.922,1,.961,.922,1,.961,.922]));
        const uniforms: Record<string, number[]> = {
          u_shape:[1.32,.49,.84,.01], u_surface:[1.73,1.08,.07,2],
          u_finish:[2.27,0,.040,.35], u_transform:[4984,3.37,.40,1],
          u_space:[-.13,.05,0,0], u_cursor:[0,3,.54,.56],
        };
        Object.entries(uniforms).forEach(([name,value]) => gl!.uniform4fv(gl!.getUniformLocation(program!, name), value));
        scene = gl!.getUniformLocation(program, 'u_scene');
        canvas.dataset.status = 'ready'; resize();
      } catch (error) {
        console.error('Waves background:', error); canvas.dataset.status = 'unavailable'; cleanupGL();
      }
    }
    function draw(now: number) {
      frame = 0;
      if (!program || document.hidden || !inView || gl!.isContextLost()) return;
      const animate = shouldAnimate(reduced.matches, pausedRef.current);
      if (!limiter.shouldRender(now, dirty)) { frame = requestAnimationFrame(draw); return; }
      const elapsed = clock.tick(now, animate);
      gl!.uniform4f(scene, canvas.width, canvas.height, elapsed * -.67, 4);
      gl!.drawArrays(gl!.TRIANGLES, 0, 3);
      dirty = false;
      canvas.dataset.motion = animate ? 'running' : reduced.matches ? 'reduced' : 'paused';
      // Low-frequency diagnostics let browser QA verify real time advances.
      if (++frames === 1 || frames % 12 === 0) {
        canvas.dataset.time = elapsed.toFixed(3); canvas.dataset.frames = String(frames);
      }
      if (animate) frame = requestAnimationFrame(draw);
    }
    function schedule() {
      halt(); dirty = true;
      if (document.hidden) canvas.dataset.motion = 'hidden';
      else if (!inView) canvas.dataset.motion = 'offscreen';
      else if (program) frame = requestAnimationFrame(draw);
    }
    function resize() {
      // Layout and buffer allocation happen on size changes, not on every frame.
      const rect = canvas.getBoundingClientRect();
      const [width, height] = drawingSize(rect.width, rect.height, devicePixelRatio);
      if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
      gl!.viewport(0, 0, width, height); schedule();
    }
    const lost = (event: Event) => { event.preventDefault(); halt(); canvas.dataset.status = 'lost'; };
    const restored = () => { cleanupGL(); setup(); };
    const observer = new ResizeObserver(resize); observer.observe(canvas);
    const intersection = new IntersectionObserver(entries => {
      inView = entries.some(entry => entry.isIntersecting); schedule();
    }, { rootMargin: '-84px 0px 0px 0px' });
    intersection.observe(canvas);
    updateRef.current = schedule;
    document.addEventListener('visibilitychange', schedule);
    reduced.addEventListener('change', schedule);
    canvas.addEventListener('webglcontextlost', lost);
    canvas.addEventListener('webglcontextrestored', restored);
    setup();
    return () => {
      halt(); observer.disconnect(); intersection.disconnect(); updateRef.current = () => {};
      document.removeEventListener('visibilitychange', schedule);
      reduced.removeEventListener('change', schedule);
      canvas.removeEventListener('webglcontextlost', lost); canvas.removeEventListener('webglcontextrestored', restored);
      cleanupGL();
    };
  }, []);
  return <div className="waves-backdrop" aria-hidden="true"><canvas ref={ref} className="waves" /></div>;
}
